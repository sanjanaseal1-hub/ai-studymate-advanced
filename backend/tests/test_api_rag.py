"""API tests for the advanced RAG flow (fake Gemini, real Chroma + SQLite in temp dirs)."""
import json

import pytest
from chromadb.api.shared_system_client import SharedSystemClient

from main import app
from prompts.rag_prompt import NOT_ENOUGH_INFO
from services.document_repository import DocumentRepository, get_document_repository
from services.vector_store import VectorStore, get_vector_store
from tests.helpers import BIO, COOK, MD_DOC, make_encrypted_pdf, make_pdf
from utils.errors import LLMError


def upload(env, *files, **data):
    return env.client.post("/api/documents/upload", files=[("files", f) for f in files], data=data)


def docs(env):
    return env.client.get("/api/documents").json()["documents"]


@pytest.fixture
def loaded(env):
    """A PDF, a TXT and a Markdown document, all indexed."""
    r = upload(env, ("biology.pdf", make_pdf([COOK, BIO]), "application/pdf"), ("cooking.txt", (COOK * 3).encode(), "text/plain"),
               ("genetics.md", MD_DOC.encode(), "text/markdown"))
    assert r.status_code == 202
    return env


def ask(env, question="What is DNA replication?", **extra):
    return env.client.post("/api/qa", json={"question": question, **extra})


# ---------- health / errors format ----------
def test_health_ready_request_id_and_error_format(env):
    assert env.client.get("/api/health").json() == {"status": "ok"}
    ready = env.client.get("/api/ready")
    assert ready.status_code == 200 and ready.json()["checks"]["document_db"] and ready.json()["checks"]["vector_store"]
    assert "sk" not in ready.text and env.client.get("/api/health", headers={"X-Request-ID": "abc123"}).headers["x-request-id"] == "abc123"
    missing = env.client.get("/api/nope")
    assert missing.status_code == 404 and missing.json()["success"] is False and "request_id" in missing.json()


# ---------- upload + background indexing ----------
def test_upload_pdf_txt_md_are_queued_then_indexed_with_metadata(loaded):
    listing = docs(loaded)
    assert {d["file_type"] for d in listing} == {"pdf", "txt", "md"} and all(d["status"] == "indexed" for d in listing)
    assert all(d["chunks"] > 0 and d["indexed_at"] and d["created_at"] for d in listing)
    pdf = next(d for d in listing if d["file_type"] == "pdf")
    assert pdf["pages"] == 2
    assert loaded.store.stats("default")[0] == 3


def test_upload_response_is_202_with_queued_status(env):
    r = upload(env, ("a.txt", BIO.encode(), "text/plain"), auto_index="false")
    assert r.status_code == 202 and r.json()["documents"][0]["status"] == "queued"
    assert docs(env)[0]["status"] == "queued" and env.store.stats("default") == (0, 0)       # not indexed until triggered
    doc_id = r.json()["documents"][0]["id"]
    assert env.client.post(f"/api/documents/{doc_id}/index").status_code == 202
    assert env.client.get(f"/api/documents/{doc_id}").json()["document"]["status"] == "indexed"


def test_upload_validation_errors(env):
    assert env.client.post("/api/documents/upload").status_code == 400
    assert upload(env, ("a.docx", b"x", "application/octet-stream")).status_code == 415
    assert upload(env, ("e.txt", b"  ", "text/plain")).status_code == 422
    assert upload(env, ("fake.pdf", b"not a pdf", "application/pdf")).status_code == 422
    assert upload(env, *[(f"f{i}.txt", b"x", "text/plain") for i in range(6)]).status_code == 422
    assert docs(env) == []


def test_oversized_upload(env, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")
    r = upload(env, ("big.txt", b"a" * 5000, "text/plain"))
    assert r.status_code == 413 and "too large" in r.json()["error"]


def test_partial_upload_reports_per_file_errors(env):
    r = upload(env, ("ok.txt", BIO.encode(), "text/plain"), ("bad.docx", b"x", "text/plain"))
    assert r.status_code == 202 and len(r.json()["documents"]) == 1 and r.json()["errors"][0]["filename"] == "bad.docx"


def test_corrupted_encrypted_and_scanned_documents_fail_with_friendly_message(env):
    upload(env, ("corrupt.pdf", b"%PDF-1.4 garbage garbage", "application/pdf"), ("locked.pdf", make_encrypted_pdf(), "application/pdf"),
           ("scan.pdf", make_pdf([""]), "application/pdf"))
    by_name = {d["filename"]: d for d in docs(env)}
    assert all(d["status"] == "failed" for d in by_name.values())
    assert "corrupted" in by_name["corrupt.pdf"]["error"] and "password-protected" in by_name["locked.pdf"]["error"]
    assert "No readable text" in by_name["scan.pdf"]["error"] and env.store.stats("default") == (0, 0)


def test_duplicate_upload_is_not_indexed_twice(env):
    first = upload(env, ("a.txt", BIO.encode(), "text/plain")).json()["documents"][0]
    calls = env.embedder.calls
    second = upload(env, ("renamed.txt", BIO.encode(), "text/plain")).json()["documents"][0]
    assert second["id"] == first["id"] and second["duplicate"] is True and env.embedder.calls == calls and len(docs(env)) == 1


def test_embedding_failure_marks_failed_and_retry_succeeds_without_duplicates(env):
    env.embedder.error = LLMError(429, "Too many requests right now.")
    doc = upload(env, ("a.txt", (BIO * 4).encode(), "text/plain")).json()["documents"][0]
    state = env.client.get(f"/api/documents/{doc['id']}").json()["document"]
    assert state["status"] == "failed" and "Too many requests" in state["error"] and env.store.stats("default") == (0, 0)
    env.embedder.error = None
    assert env.client.post(f"/api/documents/{doc['id']}/index").status_code == 202
    ok = env.client.get(f"/api/documents/{doc['id']}").json()["document"]
    assert ok["status"] == "indexed" and env.store.stats("default") == (1, ok["chunks"])


def test_reindex_is_idempotent_and_requires_force(loaded):
    doc = docs(loaded)[0]
    before = loaded.store.stats("default")
    assert loaded.client.post(f"/api/documents/{doc['id']}/index").status_code == 409
    assert loaded.client.post(f"/api/documents/{doc['id']}/index?force=true").status_code == 202
    assert loaded.store.stats("default") == before and loaded.client.post("/api/documents/zzz/index").status_code == 404


def test_delete_removes_document_chunks_and_file(loaded):
    doc = next(d for d in docs(loaded) if d["filename"] == "biology.pdf")
    assert loaded.client.delete(f"/api/documents/{doc['id']}").json()["deleted_id"] == doc["id"]
    assert doc["id"] not in {d["id"] for d in docs(loaded)} and loaded.store.stats("default")[0] == 2
    assert not (loaded.repo.upload_dir / f"{doc['id']}.bin").exists()
    assert loaded.client.delete(f"/api/documents/{doc['id']}").status_code == 404


# ---------- question answering ----------
def test_question_validation_and_no_documents(env):
    assert env.client.post("/api/qa", json={"question": "  "}).status_code == 422
    assert env.client.post("/api/qa", json={"question": "x" * 1001}).status_code == 422
    assert env.client.post("/api/qa", json={"question": "q", "document_ids": ["bad id!"]}).status_code == 422
    r = ask(env)
    assert r.status_code == 409 and "No indexed documents" in r.json()["error"] and env.llm.calls == 0


def test_grounded_answer_has_citations_sources_diagnostics(loaded):
    body = ask(loaded).json()
    assert body["success"] and body["state"] == "grounded" and body["grounded"] and body["answer"].startswith("DNA replication")
    assert body["confidence"]["label"] in ("high", "medium", "low") and body["confidence"]["score"] > 0
    used = [s for s in body["sources"] if s["status"] == "used"]
    assert used[0]["citation"] == 1 and used[0]["document"] == "biology.pdf" and used[0]["page"] == 2 and used[0]["cited"]
    assert {"vector_score", "lexical_score", "final_score", "chunk_index", "text", "rank"} <= used[0].keys()
    assert body["citations"][0] == {"number": 1, "document_id": used[0]["document_id"], "document": "biology.pdf", "page": 2,
                                    "heading": None, "chunk_index": used[0]["chunk_index"]}
    d = body["retrieval_diagnostics"]
    assert d["documents_searched"] == 3 and d["chunks_searched"] >= 3 and d["top_k"] == 3 and d["candidate_k"] == 8
    assert d["similarity_threshold"] == 0.3 and d["chunks_used"] == len(used) and "embedding" in d["timings_ms"]
    assert "helicase" in loaded.llm.prompt and "[1]" in loaded.llm.prompt and "<context>" in loaded.llm.prompt
    assert loaded.llm.temperature == 0.1                                  # low, deterministic-leaning generation


def test_markdown_heading_metadata_reaches_sources(loaded):
    loaded.llm.text = "Frameshift mutations shift the reading frame [1]."
    body = ask(loaded, "What are frameshift mutations?").json()
    top = body["sources"][0]
    assert top["document"] == "genetics.md" and top["heading"] == "Genetics Guide > Mutations > Types" and top["page"] is None
    assert "section: Genetics Guide > Mutations > Types" in loaded.llm.prompt


def test_source_statuses_used_excluded_below_threshold(loaded):
    body = ask(loaded, "What is DNA replication helicase mutation sourdough?").json()
    statuses = [s["status"] for s in body["sources"]]
    assert statuses.count("used") <= 3 and set(statuses) <= {"used", "excluded", "below_threshold"}
    assert statuses == sorted(statuses, key=["used", "excluded", "below_threshold"].index)   # used first
    below = [s for s in body["sources"] if s["status"] == "below_threshold"]
    assert below and all(s["final_score"] is None and s["citation"] is None for s in below)


def test_irrelevant_question_returns_no_evidence_without_calling_llm(loaded):
    body = ask(loaded, "Who won the football world cup in 1998?").json()
    assert body["state"] == "no_evidence" and body["grounded"] is False and "could not find sufficiently relevant" in body["answer"]
    assert loaded.llm.calls == 0 and body["retrieval_diagnostics"]["chunks_used"] == 0
    assert all(s["status"] == "below_threshold" for s in body["sources"]) and body["warnings"]


def test_threshold_is_configurable(loaded, monkeypatch):
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.99")
    assert ask(loaded, "DNA replication copies DNA").json()["state"] == "no_evidence"


def test_model_refusal_is_reported_as_insufficient(loaded):
    loaded.llm.text = NOT_ENOUGH_INFO
    body = ask(loaded).json()
    assert body["state"] == "insufficient" and body["grounded"] is False and body["confidence"]["label"] == "none"


def test_invalid_citations_are_stripped_and_warned(loaded):
    loaded.llm.text = "DNA replication copies DNA [1]. It also cures colds [9]."
    body = ask(loaded).json()
    assert "[9]" not in body["answer"] and body["grounded"] and any("invalid citation" in w for w in body["warnings"])


def test_answer_without_citations_is_flagged(loaded):
    loaded.llm.text = "DNA replication is the way cells copy their genetic material before they divide."
    body = ask(loaded).json()
    assert body["state"] == "ungrounded" and body["grounded"] is False and body["warnings"]


def test_document_filter_restricts_search(loaded):
    cooking = next(d for d in docs(loaded) if d["filename"] == "cooking.txt")
    body = ask(loaded, "sourdough bread flour", document_ids=[cooking["id"]]).json()
    assert {s["document"] for s in body["sources"]} == {"cooking.txt"} and body["retrieval_diagnostics"]["documents_searched"] == 1
    assert ask(loaded, document_ids=["doesnotexist"]).status_code == 404


def test_filtering_by_unindexed_document_is_rejected(env):
    doc = upload(env, ("a.txt", BIO.encode(), "text/plain"), auto_index="false").json()["documents"][0]
    r = ask(env, document_ids=[doc["id"]])
    assert r.status_code == 409 and "not indexed" in r.json()["error"]


def test_llm_and_embedding_failures_are_friendly(loaded):
    loaded.llm.error = LLMError(500, "The AI service is not configured correctly.", "secret detail")
    r = ask(loaded)
    assert r.status_code == 500 and r.json()["success"] is False and "secret detail" not in r.text
    loaded.llm.error = None
    loaded.embedder.error = LLMError(504, "The AI took too long to respond.")
    assert ask(loaded).status_code == 504


# ---------- streaming (SSE) ----------
def sse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_stream_emits_stages_tokens_and_validated_result(loaded):
    loaded.llm.text = "DNA replication copies DNA [1] and [9]."
    r = loaded.client.post("/api/qa/stream", json={"question": "What is DNA replication?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r.text)
    stages = [d["stage"] for n, d in events if n == "stage"]
    assert stages == ["embedding", "retrieving", "reranking", "generating", "validating"]
    tokens = "".join(d["text"] for n, d in events if n == "token")
    assert "[9]" in tokens                                    # raw tokens are streamed as generated...
    final = events[-1]
    assert final[0] == "result" and "[9]" not in final[1]["answer"] and final[1]["grounded"]   # ...the result is validated


def test_stream_no_evidence_skips_generation_and_errors_are_events(loaded):
    events = sse_events(loaded.client.post("/api/qa/stream", json={"question": "Who won the 1998 football cup?"}).text)
    assert [n for n, _ in events][-1] == "result" and events[-1][1]["state"] == "no_evidence" and "generating" not in [d.get("stage") for _, d in events]
    loaded.llm.error = LLMError(504, "The AI took too long to respond.")
    events = sse_events(loaded.client.post("/api/qa/stream", json={"question": "What is DNA replication?"}).text)
    assert events[-1] == ("error", {"error": "The AI took too long to respond.", "status": 504})
    assert loaded.client.post("/api/qa/stream", json={"question": ""}).status_code == 422


# ---------- persistence across restart ----------
def test_indexed_data_survives_backend_restart(loaded):
    before = docs(loaded)
    SharedSystemClient.clear_system_cache()                  # simulate a new process: reopen the same files
    app.dependency_overrides[get_vector_store] = lambda: VectorStore(loaded.tmp_path / "chroma", "test")
    app.dependency_overrides[get_document_repository] = lambda: DocumentRepository(loaded.tmp_path / "docs.db", loaded.tmp_path / "uploads")
    assert docs(loaded) == before
    body = ask(loaded).json()
    assert body["state"] == "grounded" and body["sources"][0]["document"] == "biology.pdf"


def test_interrupted_jobs_are_marked_failed_on_restart(env):
    doc = upload(env, ("a.txt", BIO.encode(), "text/plain"), auto_index="false").json()["documents"][0]
    env.repo.update(doc["id"], status="processing")
    assert env.repo.recover_interrupted() == 1
    state = env.client.get(f"/api/documents/{doc['id']}").json()["document"]
    assert state["status"] == "failed" and "restart" in state["error"]
