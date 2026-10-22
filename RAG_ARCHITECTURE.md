# RAG Architecture (Advanced Level)

## 1. End-to-end flow
```
INGESTION (background job)                          QUESTION ANSWERING (SSE)
upload → validate → store raw file + SQLite row     question → embed (RETRIEVAL_QUERY)
       → [202 returned]                                      → Chroma cosine search, CANDIDATE_K=15
       → extract (PDF pages / MD sections / TXT)             → relevance threshold on vector score
       → clean → structure-aware chunk                       → hybrid re-rank (vector + BM25) → TOP_K=4
       → embed (RETRIEVAL_DOCUMENT, batches of 100)          → numbered context + strict prompt
       → delete old chunks → upsert to Chroma                → Gemini (temperature 0.1, streamed)
       → status: indexed | failed                            → validate citations → result + diagnostics
```
Responsibilities: `routes/` HTTP only · `services/ingestion_service` job orchestration · `extraction_service`, `chunking_service` parsing · `embedding_service`, `llm_client` provider layer (swappable ABCs) · `vector_store` Chroma repository · `document_repository` SQLite registry · `reranker`, `answer_validation`, `rag_service` retrieval and generation logic · `prompts/` templates · `models/schemas` Pydantic contracts · `utils/config` environment.

## 2. Why each component
| Component | Why |
|---|---|
| FastAPI + Pydantic | typed validation, automatic OpenAPI docs, async I/O for API calls and streaming |
| ChromaDB (persistent) | free, embedded (no server), disk-persistent HNSW index with metadata filters; fits laptops and a single Docker volume. Alternatives (pgvector, Qdrant) are better for multi-user scale but need a service |
| SQLite registry | document-level state (queued/processing/indexed/failed, errors, counts) is relational and tiny; standard library, no extra service. Chroma holds only chunks |
| Gemini embeddings + generation | one provider/key; separate models for embedding and generation; both behind interfaces so another provider is a new subclass |
| BM25 + vector re-rank | cheap, local, explainable (see §7) |
| React + SSE | progressive answer and stage display; SSE is simpler than WebSockets for one-way streams |
| Docker Compose | one command, persistent volume, nginx handles SPA + proxy |

## 3. Parsing and preprocessing
- **Validation at upload:** extension (.pdf/.txt/.md/.markdown), size limit, empty file, `%PDF-` signature, binary (NUL) and undecodable text. Deeper checks run in the job: corrupted PDF, encrypted PDF (empty-password PDFs are unlocked; others refused with a clear message), PDFs with no extractable text (scans).
- **PDF:** one `Page` per page (page number kept); a bad page is skipped, not fatal. **TXT:** UTF-8, cp1252 fallback. **Markdown:** split at `#` headings (ignoring `#` inside code fences) into sections carrying a heading path such as `Guide > Mutations > Types`.
- **Cleaning:** Unicode NFKC, control characters removed, whitespace normalised; PDF/TXT additionally get de-hyphenation (`exam-\nple`→`example`) and line-wrap repair; Markdown keeps its line structure (lists, code). Paragraph breaks are preserved everywhere.

## 4. Chunking strategy
Sections (page / heading) are never mixed. Inside a section: **paragraphs are packed** up to `CHUNK_SIZE`; a paragraph that is too long is split **at sentence boundaries**; a single oversized sentence is **hard-split** as a last resort. A new chunk starts with a **sentence-aligned overlap** (≤ `CHUNK_OVERLAP`) from the previous chunk. Duplicate chunks (normalised-text hash) are dropped; tiny headless fragments (< `MIN_CHUNK_CHARS`, e.g. stray page numbers) are merged or dropped, but a short section *with a heading* is kept. A heading is prepended to the text that is embedded and BM25-scored, so “Inheritance: …” is findable by its title.

**Values:** `CHUNK_SIZE=1000` characters (~250 tokens, about one paragraph), `CHUNK_OVERLAP=150` (15%, about a sentence), `MIN_CHUNK_CHARS=80`. One paragraph ≈ one idea keeps vectors specific; 4 chunks ≈ 1,000 prompt tokens: enough evidence, cheap, readable in the UI. The embedding limit (2,048 tokens) is not the constraint; precision is. *Too small:* fragments lose context (“it then unwinds…”). *Too large:* several topics share one vector, similarity is diluted and irrelevant text reaches the LLM. *Overlap:* an answer straddling a boundary stays retrievable. These are reasonable defaults, not tuned on a labelled set; all are env variables.

## 5. Embeddings
`gemini-embedding-001`, 768 dimensions (configurable), separate from the generation model. Chunks use task type `RETRIEVAL_DOCUMENT`, questions `RETRIEVAL_QUERY`, so a question lands near the passages that answer it. Requests are batched (100 per call) and retried with exponential backoff on 429/5xx/timeouts/network errors (`LLM_MAX_RETRIES`). Meaning-based vectors match paraphrases that keyword search misses.

## 6. Persistent vector database and retrieval
Chroma `PersistentClient` at `CHROMA_PATH`, collection `CHROMA_COLLECTION`, cosine distance (similarity = 1 − distance). Each chunk is stored with: `document_id`, `user_id`, `filename`, `file_type`, `page`, `heading`, `chunk_index`, `upload_time`, `indexed_at`, `embedding_model`. Chunk IDs are `<document_id>:<index>` and re-indexing first deletes the document's chunks, so **retries never duplicate**. Identical uploads (SHA-256) are not indexed twice. `user_id` and `document_ids` filters are applied inside the vector query, which is also how per-user separation will work once authentication supplies the user.

## 7. Re-ranking
1. Retrieve `CANDIDATE_K=15` candidates by cosine similarity.
2. **Gate** by `SIMILARITY_THRESHOLD` (on the semantic score; weak matches are never used).
3. Score survivors with **BM25** against the question (heading included), normalise to 0–1.
4. `final = α·vector + (1−α)·bm25`, `α = RERANK_ALPHA = 0.7`; keep `TOP_K=4`.

*Why:* vectors capture meaning but can rank a passage with the exact term (an error code, name, acronym) too low; BM25 rewards exact overlap. *Trade-offs:* no extra model or download, milliseconds of cost, fully explainable; but BM25 statistics come from the candidate set only, synonyms are left to the vector score, and a cross-encoder would be more accurate at higher cost. Every candidate's original (`vector_score`), BM25 (`lexical_score`) and `final_score` are returned and shown. Tests prove an exact-match chunk is promoted over a slightly higher vector score, and that `α=1` reproduces pure vector order.

## 8. Relevance threshold
`SIMILARITY_THRESHOLD=0.5`. If no candidate passes, the LLM is **not called** and the user gets “I could not find sufficiently relevant information…” (`state: no_evidence`). The value is a starting point for this embedding model, not calibrated on data: use the scores in the UI (relevant vs unrelated questions) to tune it.

## 9. Grounding and citation validation
**Prompt:** system role + task + numbered excerpts `[1]…[n]` (with filename/page/section) + question + rules: use only the excerpts; reply with an exact sentence when unsupported; state partial coverage; flag contradictions; cite every claim as `[n]`; never invent citations, pages or file names. Excerpts/questions are fenced as data. Temperature `RAG_TEMPERATURE=0.1`.

**Validation (after generation):** every `[n]` is checked against the number of sources actually sent; invalid ones are removed and reported in `warnings`; the model's own refusal is detected (`state: insufficient`); an answer with no valid citation is flagged `ungrounded`; citation coverage (share of substantial sentences with a citation) adds a warning when low; `confidence` is a documented *heuristic* (mean similarity of cited chunks × coverage, reduced for invalid citations): a signal, not a probability. **It does not verify that a cited chunk truly entails the sentence.**

Response: `answer`, `state` (`grounded|insufficient|ungrounded|no_evidence`), `grounded`, `confidence`, `citations`, `sources` (each `used|excluded|below_threshold`, `citation`, `cited`, scores, metadata, text), `retrieval_diagnostics` (documents/chunks searched, candidates, thresholds, timings), `warnings`.

## 10. Hallucination-reduction measures (and their limits)
Retrieval before generation · threshold gate · re-ranking · strict prompt · low temperature · numbered sources · citation validation · explicit refusal paths · sources and diagnostics visible so the user can check. These **lower** the chance of unsupported answers. The model can still misread or over-generalise correctly retrieved text, and retrieval can miss the right passage.

## 11. Streaming and progress
`POST /api/qa/stream` returns Server-Sent Events: `stage` (embedding → retrieving → reranking → generating → validating), `token` (real provider tokens from Gemini `streamGenerateContent?alt=sse`), then `result` (validated answer + sources) or `error`. The UI shows the stages and a draft answer, then replaces the draft with the **validated** answer (the draft may briefly contain a citation that validation later removes). The Stop button aborts the request; the server checks for disconnects between events and closes the provider stream. Providers without streaming fall back to one chunk. Caveat: the streaming client was verified against a local stub speaking Gemini's SSE format, not against Google's live service.

## 12. Error handling and reliability
One error shape `{success:false, error, request_id}`. Provider failures map to safe messages (key → 500, rate limit → 429, 5xx → 503, timeout → 504, network/malformed/empty → 502, blocked content → 422); transient ones are retried with backoff. Indexing failures set the document to `failed` with a user-readable reason and leave no half-indexed chunks (chunks are written only after all embeddings succeed); retry is safe. Jobs interrupted by a restart are marked failed on startup. Logs carry a request ID (and `[job <id>]` for ingestion); API keys and stack traces never reach users or logs.

## 13. Scalability limits and future work
In-process background tasks (→ Celery/RQ + Redis); single Chroma instance and SQLite file (→ Qdrant/pgvector + Postgres); no authentication (→ JWT, `user_id` already scopes all data); BM25 over candidates only (→ hybrid search / cross-encoder); fixed threshold (→ evaluation set, per-corpus calibration); no OCR (→ Tesseract/vision model); no claim-level entailment check (→ NLI verifier); embedding-model change needs re-indexing (→ versioned collections).
