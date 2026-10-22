# Testing

```bash
cd backend && pytest        # 82 tests, offline: no API key, no network
cd frontend && npm test     # 17 tests
```
Backend tests use **real ChromaDB and SQLite in temporary directories** and **fake Gemini clients** (`tests/helpers.py`; the fake embedder hashes words into vectors purely so tests are free and deterministic).

| Area | File | What is checked |
|---|---|---|
| Upload validation | `test_ingestion.py` | unsupported type, empty, oversized, fake PDF, binary text, accepted types |
| Extraction | `test_ingestion.py` | PDF pages, TXT UTF-8/cp1252, corrupted and password-protected PDFs, Markdown heading paths, `#` inside code fences |
| Cleaning | `test_ingestion.py` | de-hyphenation, wrap repair, control chars; Markdown structure preserved |
| Chunking | `test_ingestion.py` | size limit, sentence/paragraph boundaries, sentence-aligned overlap, hard split, tiny/duplicate removal, heading kept, metadata |
| Vector store | `test_vector_store.py` | ranking + metadata, **persistence after restart**, add without losing old docs, delete one document, idempotent upsert, document filter, user separation |
| Re-ranking | `test_retrieval.py` | BM25 behaviour, exact-match promotion over higher vector score, alpha=1 equals vector order, heading text counts |
| Citation validation | `test_retrieval.py` | valid kept, invalid removed + warned, mixed groups, ungrounded, refusal, coverage warning, confidence |
| API | `test_api_rag.py` | health/ready/request-ID/error shape; upload → queued → indexed; `auto_index=false` + manual trigger; corrupted/encrypted/scanned → failed with message; duplicates; embedding failure then safe retry (no duplicate chunks); re-index/force; delete; question validation; no documents; grounded answer structure, sources, diagnostics, low temperature; Markdown headings in sources; used/excluded/below-threshold; no-evidence skips LLM; configurable threshold; refusal; invalid citations; document filter; friendly LLM/embedding errors; SSE stages/tokens/validated result/error events; restart persistence; interrupted-job recovery |
| Study utilities | `test_api.py` | unchanged beginner tests |
| Frontend | `DocumentQA.test.jsx`, `App.test.jsx` | guidance, client-side file rejection, per-file server errors, all four statuses + retry + delete, empty question, streaming result with warnings/source groups/scores/diagnostics, citation click highlights + opens card, document filter, no-evidence state, error display, SSE parser, study utilities flows |

## Also verified manually in development (stub Gemini, real backend over HTTP)
PDF+TXT+MD+corrupted+unsupported in one upload → `202`, background indexing, per-file errors; plain and SSE answers (incremental tokens, invalid `[9]` removed); unrelated question → no-evidence; **backend process restarted → documents and answers intact**; delete → chunks gone; key never in logs.

## Not verified here (please check once with your key / Docker)
- Live Gemini calls (embeddings, generation, streaming) and the right `SIMILARITY_THRESHOLD` for your documents.
- `docker compose up --build` (no Docker in the development sandbox).
- Visual/responsive check of the UI in a real browser and the Stop-button disconnect path (implemented; no automated test).

## Manual checklist
- [ ] Upload PDF + TXT + MD together; rows go Queued → Processing → Indexed
- [ ] Upload a corrupted PDF, an encrypted PDF, a `.docx`: each shows a clear reason
- [ ] Single-document question: `[1]` links to a source card with page/section
- [ ] Multi-document question cites several files
- [ ] “Show technical details”: vector, keyword and final scores visible
- [ ] Unrelated question: “not enough information”, sources below threshold
- [ ] Restart backend / `docker compose restart`: documents still listed and answerable
