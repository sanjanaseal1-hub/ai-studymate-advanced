# AI StudyMate: Advanced RAG Assistant

A production-style Retrieval-Augmented Generation assistant: upload PDF, TXT and Markdown files, then ask questions and get **grounded, cited answers** with the evidence shown. The original **Study Utilities** (summarize, quiz, explain, improve answer) are still included in their own tab.

## Overview
Documents are validated, parsed, cleaned, chunked along their structure, embedded with Gemini, and stored in a **persistent ChromaDB** index. A question is embedded, candidate chunks are retrieved by cosine similarity, filtered by a relevance threshold, **re-ranked** (vector + BM25), and the best few are given to Gemini under a strict grounding prompt. The answer is **validated** (citations checked against the real sources) and streamed to the UI, together with sources, scores and diagnostics. See [RAG_ARCHITECTURE.md](RAG_ARCHITECTURE.md).

## Features
- **Ingestion:** PDF (per-page), TXT, Markdown (heading-aware); type/size/empty/binary/corrupted/encrypted/no-text checks with friendly errors; Unicode, control-character, whitespace and de-hyphenation cleanup
- **Structure-aware chunking:** paragraph → sentence → hard-split, sentence-aligned overlap, duplicate/tiny-chunk removal, page + heading + chunk-index metadata
- **Persistent vector DB:** ChromaDB (cosine HNSW); survives restarts; add/delete/list documents; no duplicate indexing; `user_id` + `document_id` metadata for per-user separation and per-document filtering
- **Background indexing:** upload returns `202`; jobs go queued → processing → indexed/failed; safe retry/re-index; interrupted jobs recovered on startup
- **Retrieval quality:** candidate retrieval (15) → threshold → hybrid re-rank (vector + BM25) → top 4; diagnostics with original and re-ranked scores
- **Grounded answers:** strict prompt, numbered `[n]` citations, temperature 0.1, post-generation citation validation, `grounded` / `confidence` / `warnings`, honest "not enough information" state
- **SSE streaming:** stage events + progressive tokens; Stop button; server stops generating when the client disconnects
- **UI:** drag-and-drop multi-upload, per-file status, document list with delete/retry/“search only this document”, clickable citations → source cards, used / excluded / below-threshold groups, technical-details panel
- **Ops:** request-ID logging, `/api/health` + `/api/ready`, OpenAPI docs at `/docs`, Docker Compose with a persistent volume

## Technology stack
FastAPI · Pydantic · ChromaDB · SQLite (document/job registry) · Gemini API (generation + embeddings, behind `LLMClient`/`EmbeddingClient`) · pypdf · React 18 + Vite · nginx (Docker) · pytest · Vitest.

## Architecture
```
Browser (React) ──/api──> FastAPI
  upload ──> validate ──> SQLite registry (queued) + raw file ──202──> background job:
            extract (pypdf / md sections) → clean → chunk → embed (Gemini, batched, retried) → Chroma upsert
  ask ────> embed question → Chroma search (candidates) → threshold → BM25+vector re-rank → top-k
            → grounded prompt → Gemini (streamed) → citation validation → SSE: stage/token/result
backend/  routes/ (HTTP)  services/ (ingestion, chunking, vector_store, reranker, rag_service, answer_validation, llm_client…)
          prompts/  models/schemas.py  utils/ (config, errors, logging)  tests/
frontend/ src/pages  src/components  src/services (api, ragApi, sse)
```

## Local setup (without Docker)
Requirements: Python 3.10–3.13 recommended (ChromaDB ships binary dependencies; the Docker image uses 3.12), Node 18+, a [Gemini API key](https://aistudio.google.com/apikey).
```bash
cp .env.example .env            # Windows: copy .env.example .env, then add GEMINI_API_KEY
cd backend
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000                # API docs: http://localhost:8000/docs
# second terminal
cd frontend && npm install && npm run dev            # http://localhost:5173
```
Data is stored in `backend/data/` (git-ignored) and persists between runs.

## Docker
```bash
cp .env.example .env            # add your GEMINI_API_KEY
docker compose up --build
```
App: http://localhost:8080 · API docs: http://localhost:8000/docs. The named volume `studymate_data` holds the vector index, registry and uploads, so data survives `docker compose restart` and `down` (use `down -v` to wipe it). nginx serves the built frontend and proxies `/api` to the backend with buffering off (needed for streaming).

## Environment variables
All are listed with comments in `.env.example`: `GEMINI_API_KEY`, `GEMINI_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MIN_CHUNK_CHARS`, `CANDIDATE_K`, `TOP_K`, `SIMILARITY_THRESHOLD`, `RERANK_ALPHA`, `RAG_TEMPERATURE`, `LLM_MAX_RETRIES`, `RETRY_BACKOFF_SECONDS`, `MAX_UPLOAD_MB`, `MAX_FILES_PER_UPLOAD`, `DATA_DIR`, `CHROMA_PATH`, `CHROMA_COLLECTION`, `DEFAULT_USER_ID`, `ALLOWED_ORIGINS`.

## API summary
| Method & path | Purpose |
|---|---|
| `POST /api/documents/upload` | multipart `files` (+ optional `auto_index=false`); returns `202`, per-file errors |
| `POST /api/documents/{id}/index[?force=true]` | start / retry / re-index |
| `GET /api/documents`, `GET /api/documents/{id}` | list / status (queued, processing, indexed, failed) |
| `DELETE /api/documents/{id}` | remove record, file and all chunks |
| `POST /api/qa` | answer as JSON `{question, document_ids?}` |
| `POST /api/qa/stream` | same, as Server-Sent Events (`stage`, `token`, `result`, `error`) |
| `GET /api/health`, `GET /api/ready` | liveness / readiness |
Errors always look like `{"success": false, "error": "...", "request_id": "..."}`.

## Run the tests
```bash
cd backend && pytest        # 82 tests, no API key or network
cd frontend && npm test     # 17 tests
```
See [TESTING.md](TESTING.md).

## Demo workflow
Upload `.pdf`, `.txt`, `.md` → watch Queued → Processing → Indexed → ask a single-document question → ask one that needs several documents → click `[n]` citations → open “Show technical details” → ask an unrelated question (“not enough information”) → restart the backend and show the documents are still there. A full 3–5 minute script is in [ADVANCED_INTERVIEW_GUIDE.md](ADVANCED_INTERVIEW_GUIDE.md).

## Screenshots
_Add your screenshots here:_ `docs/screenshots/upload.png`, `docs/screenshots/answer-citations.png`, `docs/screenshots/diagnostics.png`.

## Known limitations
- These measures **reduce** hallucinations; they do not guarantee zero. The validator checks that cited numbers exist, not that the cited text truly supports each sentence.
- Scanned (image-only) PDFs need OCR, which is not included; password-protected PDFs are refused.
- Tables and figures in PDFs are flattened to text.
- One user (`DEFAULT_USER_ID`): the data model supports per-user separation but there is no authentication yet.
- Background jobs use FastAPI background tasks (in-process): jobs interrupted by a crash are marked failed and need a retry; no distributed queue.
- `SIMILARITY_THRESHOLD=0.5` and `RERANK_ALPHA=0.7` are reasoned defaults, not tuned on a labelled dataset; tune them with the scores shown in the UI.
- BM25 statistics are computed over the candidate set only.
- Changing the embedding model/dimensions requires a new collection and re-indexing.
- Docker files and the real Gemini API were not exercised in the development sandbox (see TESTING.md).

## Security notes
API key only in `.env` / environment (git-ignored), sent in a header from the backend, never to the browser, never logged. Uploads are validated (type, size, content) and stored under generated IDs, never by user-supplied filename. Retrieved text and questions are fenced as data in the prompt (basic prompt-injection mitigation, not a guarantee). Error responses hide stack traces and provider details. CORS is limited to `ALLOWED_ORIGINS`. React renders Markdown without raw HTML. Add authentication before exposing the app publicly.

## Earlier levels
[Beginner guide](docs/BEGINNER_INTERVIEW_GUIDE.md) · [Intermediate guide](docs/INTERMEDIATE_INTERVIEW_GUIDE.md)
