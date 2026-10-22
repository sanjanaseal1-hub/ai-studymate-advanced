# Advanced Interview Guide

Short, accurate answers. Numbers are this project's defaults.

**Explain the full architecture.** React talks to FastAPI. Upload validates files, stores them with a SQLite row (queued) and returns 202; a background job extracts, cleans, chunks, embeds (Gemini) and upserts into persistent ChromaDB. A question is embedded, Chroma returns 15 candidates by cosine similarity, a threshold removes weak ones, BM25 + vector re-ranking picks 4, a strict prompt with numbered sources goes to Gemini, the answer is streamed and then citation-validated; the UI shows answer, sources, diagnostics.

**Why FastAPI / React / Pydantic / Docker / Chroma?** FastAPI: async I/O for slow API calls and streaming, automatic OpenAPI docs. Pydantic: validation and typed contracts at the boundary. React: stateful UI (statuses, streaming, citations). Docker: one-command reproducible setup with a persistent volume. Chroma: free, embedded, persistent, metadata filters, no extra server; the trade-off is limited multi-user scale (pgvector/Qdrant later).

**Ingestion pipeline?** Validate (type, size, empty, signature, binary) → store raw file → job: extract (PDF per page, Markdown per heading, TXT) → clean (NFKC, control chars, de-hyphenation, wrap repair) → chunk → embed in batches → delete old chunks → upsert → status indexed/failed.

**Chunking strategy and values?** Structure-aware: never mix pages/headings; pack paragraphs; split long ones at sentences; hard-split only as a last resort; sentence-aligned overlap; drop duplicates/tiny fragments. 1000 chars (~250 tokens), 150 overlap. One paragraph ≈ one idea gives specific vectors; 4 chunks ≈ 1k tokens of context. Too small loses context; too large dilutes similarity. Defaults are reasoned, not tuned on a labelled set.

**Embeddings and similarity search?** An embedding is a vector where similar meaning is close. Same model embeds chunks (`RETRIEVAL_DOCUMENT`) and questions (`RETRIEVAL_QUERY`); Chroma ranks by cosine similarity (1 − cosine distance). It finds paraphrases that keyword search misses.

**How does persistence work?** Chroma `PersistentClient` writes to `CHROMA_PATH` (a Docker volume); the SQLite registry sits in the same data dir. On restart both reopen; jobs that were mid-flight are marked failed so the user can retry. Chunk IDs are deterministic and re-index deletes first, so no duplicates.

**Why re-rank, and how?** Vectors can miss exact terms (codes, names). We fetch 15 candidates, then score with BM25 and compute `0.7·vector + 0.3·BM25`, keep 4. Cheap and explainable; limitation: BM25 stats over candidates only, no synonyms. A cross-encoder is the more accurate, heavier alternative. Scores are shown in diagnostics.

**How is the threshold chosen/tuned?** 0.5 cosine is a starting point. Ask relevant and irrelevant questions, read the similarity scores in the UI, and set the threshold between the two groups. Too high → false “not found”; too low → irrelevant context reaches the LLM.

**How do you reduce hallucinations?** Retrieve first; threshold gate; re-rank; strict prompt (only context, exact refusal sentence, cite, no invented sources); temperature 0.1; citation validation; visible sources. These reduce, not eliminate, hallucination.

**What does citation validation do, and not do?** It checks that every `[n]` exists among the sources sent, removes invalid ones, detects refusals, flags answers without citations, measures citation coverage and derives a heuristic confidence. It does not prove a cited passage supports the sentence (that needs an entailment model).

**How does streaming work?** The endpoint is SSE: `stage` events, `token` events from Gemini's streaming API, then a `result` with the validated answer. The UI replaces the draft with the validated text. Closing the connection or pressing Stop makes the server close the provider stream.

**API validation and errors?** Pydantic models validate bodies (question length, document id format); upload validates file type/size/content; one error format with `request_id`; correct codes (415, 413, 422, 404, 409, 429, 502/503/504, 202 for queued jobs).

**Background processing?** FastAPI background tasks run a sequential job per upload; states queued → processing → indexed/failed; idempotent so retry is safe; transient API errors are retried with backoff; the UI polls the list. Limits: in-process (a crash loses running jobs; they're marked failed). A queue (Celery/RQ) is the next step.

**Testing strategy?** Real Chroma/SQLite in temp dirs with fake embedding/LLM clients, so everything is offline and deterministic: parsing, chunking, persistence, re-ranking, validation, API and SSE. Frontend tests mock the API. Not covered automatically: live Gemini, Docker, browser visuals.

**Limitations and production improvements?** No auth (add JWT; `user_id` already scopes data), in-process jobs, single-node storage, no OCR, tables flattened, untuned threshold, BM25 over candidates only, no claim-level verification. Improvements: queue + Postgres/pgvector or Qdrant, OCR, cross-encoder, evaluation set, rate limiting, observability.

---
## Demo script (3–5 minutes)
1. **Start (0:00)** `docker compose up --build` (or backend + `npm run dev`); open the app. Mention `/docs` and `/api/ready`.
2. **Upload (0:20)** drag a PDF, a TXT and a MD file together. Point out the supported-file note.
3. **Status (0:40)** show Queued → Processing → Indexed, chunk counts, page counts. Optionally upload a corrupted PDF to show a friendly failure with Retry.
4. **Single-source question (1:10)** ask something only one file answers. Show streaming stages, then the answer with `[1]`.
5. **Multi-source question (1:50)** ask something needing two files; show citations from several documents.
6. **Citations and metadata (2:20)** click `[1]`: the card opens and highlights, showing filename, page or section heading, chunk, scores, text, “cited in answer”.
7. **Diagnostics (2:50)** open “Show technical details”: documents/chunks searched, threshold, vector vs keyword vs final score, used vs excluded vs below threshold.
8. **No evidence (3:15)** ask an unrelated question; show the “not enough information” state and below-threshold sources.
9. **Persistence (3:40)** restart the backend (`docker compose restart backend`); refresh; documents are still indexed; ask again.
10. **Architecture (4:10)** show the diagram in the README: ingestion job, Chroma, re-rank, grounding, validation, SSE.
