# Intermediate Interview Guide: Document Q&A (RAG)

Short, correct answers. Numbers are from THIS project.

**What is RAG?** Retrieval-Augmented Generation: retrieve relevant passages from your own data, put them in the prompt, and have the LLM answer from them.

**Why was it needed?** The task asks for answers from uploaded documents. An LLM alone answers from training memory, can't know the student's files, and can invent facts. RAG ties answers to the documents and shows the evidence.

**What is document ingestion?** Everything done before questions: upload -> extract text -> clean -> chunk -> attach metadata -> embed -> index.

**Why extract text?** Models and embeddings work on text, not on PDF/TXT file bytes. PDFs are read page by page (`pypdf`) to keep page numbers.

**Why chunk?** One vector per whole document is too vague and a whole document is too big/noisy for the prompt. Chunks give precise retrieval and short context.

**How did you choose chunk size and overlap?** 1000 characters (~250 tokens, about a paragraph) because study text has about one idea per paragraph; small enough for precise matching, big enough to carry context; four of them is ~1000 tokens of prompt. Overlap 150 (15%, about a sentence) so answers crossing a boundary stay retrievable. Both are env variables. Too small = fragments with no context; too large = diluted vectors and noisy context.

**What are embeddings / why use them?** Number vectors (768 dims, `gemini-embedding-001`) where similar meaning = nearby vectors. They match by meaning, so a question can find a passage using different words; keyword matching can't.

**How is the question embedded?** With the same model, task type `RETRIEVAL_QUERY` (chunks use `RETRIEVAL_DOCUMENT`), so both are in one space.

**What is vector similarity / which metric?** Cosine similarity: how closely two vectors point the same way. I normalise vectors, so it is just a dot product.

**What is top-k?** Score every chunk against the question, sort, keep the k best (`TOP_K=4`).

**What is a vector store?** A structure holding vectors with their chunk metadata and supporting similarity search. Mine is an in-memory numpy matrix (exact search, no server). Production: FAISS, Chroma, pgvector.

**How does retrieval happen?** Question -> embedding -> `matrix @ query` over all chunks of all documents -> sort -> top-k -> drop those below the threshold.

**How is context passed to the LLM?** The surviving chunks are numbered `[Source 1]`, `[Source 2]` with document and page, put inside `<context>` tags in the prompt with the question and strict rules (`prompts/rag_prompt.py`).

**How do you ensure grounded answers?** Retrieval first, threshold, a prompt that says "only the context, otherwise say you don't have enough information, cite sources", low temperature, and showing sources. I say "reduce", not "eliminate": the model can still misread context.

**What if the answer isn't in the documents?** Either no chunk passes the threshold (LLM not called, fixed message) or the model returns the exact "not enough information" sentence. Both set `grounded: false` and the UI says "not found in documents".

**How does the threshold help?** Top-k always returns *something*, even for an off-topic question. The threshold (0.5) stops weak matches from being treated as evidence. It's a tunable starting value; the UI's similarity scores let me tune it.

**How are sources displayed?** Each retrieved chunk shows document, page (or chunk number for TXT), similarity score and bar, full text, and whether it was used or fell below the threshold, plus a summary (chunks searched, top-k, threshold).

**Multiple documents?** All chunks go into one index with `document_id`/filename metadata; a search ranks across all documents, so one answer can cite several files.

**PDF vs TXT?** PDF: parsed per page, page number kept, may be corrupted/encrypted/scanned (image-only fails with a clear message). TXT: decoded UTF-8 (cp1252 fallback), no pages, so the source shows a chunk number.

**Limitations?** Index lost on restart, scanned PDFs unsupported, tables flattened, fixed-size character chunking, one fixed threshold, no re-ranking, single user.

**Improvements?** Persistent vector DB, OCR, heading-aware chunking, hybrid keyword+vector search with re-ranking, evaluation set to tune chunk size/threshold, user accounts, streaming.

**How did you test without paying for API calls?** FastAPI dependency overrides with fake embedding/LLM clients (tests only); a real PDF is generated in tests; I also ran an end-to-end HTTP test against a local Gemini-shaped stub. Real Gemini calls are checked manually (see TESTING.md).

**Be ready to demo:** upload a PDF + a TXT, index, ask a question answered by one, ask a question needing both, ask something off-topic and show the threshold behaviour and the similarity scores.
