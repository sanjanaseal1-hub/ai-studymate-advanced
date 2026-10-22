# Requirements → Implementation

| # | Requirement | Implemented in |
|---|---|---|
| 1 | PDF/TXT/MD ingestion; type, size, empty, corrupted, encrypted, invalid-content validation | `extraction_service.validate_upload/extract_pages`, `routes/documents.py`; friendly errors shown per file in `DocumentList` |
| 1 | Metadata: filename, id, type, page, heading, chunk index, upload/index time | `Chunk`, `VectorStore.upsert_chunks`, `document_repository` |
| 1 | Cleaning: Unicode, whitespace, control chars, de-hyphenation, wrap repair, keep paragraphs/headings | `chunking_service.clean_text` |
| 1 | Markdown-aware parsing; multi-file upload; per-file status | `_extract_markdown`; `UploadPanel`, `DocumentList` (uploading/queued/processing/indexed/failed) |
| 2 | Structure-aware, configurable chunking; no empty/duplicate/tiny chunks; tests; rationale | `chunk_document/split_section`; env `CHUNK_*`; `test_ingestion.py`; RAG_ARCHITECTURE §4 |
| 3 | Persistent vector DB (Chroma): persists, metadata, add/delete/list, no duplicate indexing, user-separable | `services/vector_store.py`, `document_repository.py`; `test_vector_store.py`, restart test |
| 4 | Separate embedding model, batching, configurable TOP_K/threshold/embedding, document filter, diagnostics, “not enough info” | `embedding_service.py`, `config.py`, `QARequest.document_ids`, `RetrievalDiagnostics`, `rag_service.py` |
| 5 | Re-ranking (BM25 + vector), configurable candidates/top-k, both scores shown, tests, docs | `reranker.py`, `CANDIDATE_K`, `RERANK_ALPHA`; `test_retrieval.py`; RAG_ARCHITECTURE §7 |
| 6 | Strict prompt, numbered sources, low temperature, validation step, structured response, honest docs | `prompts/rag_prompt.py`, `answer_validation.py`, `QAResponse`; README limitations |
| 7 | Citations map to sources; source panel fields; click-to-highlight; used/excluded/below-threshold | `AnswerView`, `SourceCards` |
| 8 | SSE streaming, stages, cancellation/disconnect | `POST /api/qa/stream`, `GeminiClient.stream`, `sse.js`, Stop button |
| 9 | Upload, index, status, list, delete, ask, stream, health/ready; schemas, errors, CORS, OpenAPI | `routes/*`, `models/schemas.py`, `main.py` |
| 10 | Background jobs, states, safe retries, API failure handling, structured logging with IDs | `ingestion_service.py`, `gemini_post` retry, `logging_utils.py`, `recover_interrupted` |
| 11 | Frontend: drag-drop, guidance, statuses, delete, validation, streaming, citations, source cards, diagnostics, no-evidence state, responsive | `frontend/src/pages/DocumentQA.jsx` + components, `styles.css` |
| 12 | Dockerfiles, compose with volume, `.env.example`, local run, nothing sensitive committed | `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, `.gitignore` (**Docker not run in sandbox**) |
| 13 | Tests (no paid calls), fakes, existing tests kept | 82 backend + 17 frontend; see TESTING.md |
| 14 | README, RAG_ARCHITECTURE, TESTING, ADVANCED_INTERVIEW_GUIDE (+demo script), `.env.example`, compose | repository root |
