from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app
from services.document_repository import DocumentRepository, get_document_repository
from services.embedding_service import get_embedding_client
from services.llm_client import get_llm_client
from services.vector_store import VectorStore, get_vector_store
from tests.helpers import FakeEmbedder, FakeLLM


@pytest.fixture
def env(tmp_path, monkeypatch):
    """App wired to a temp-dir Chroma + SQLite and fake Gemini clients. No network, no API key."""
    for key, value in {"SIMILARITY_THRESHOLD": "0.3", "TOP_K": "3", "CANDIDATE_K": "8", "LLM_MAX_RETRIES": "0",
                       "RETRY_BACKOFF_SECONDS": "0", "CHUNK_SIZE": "600", "CHUNK_OVERLAP": "80", "MIN_CHUNK_CHARS": "40"}.items():
        monkeypatch.setenv(key, value)
    ns = SimpleNamespace(store=VectorStore(tmp_path / "chroma", "test"),
                         repo=DocumentRepository(tmp_path / "docs.db", tmp_path / "uploads"),
                         embedder=FakeEmbedder(), llm=FakeLLM(), tmp_path=tmp_path)
    app.dependency_overrides[get_vector_store] = lambda: ns.store
    app.dependency_overrides[get_document_repository] = lambda: ns.repo
    app.dependency_overrides[get_embedding_client] = lambda: ns.embedder
    app.dependency_overrides[get_llm_client] = lambda: ns.llm
    ns.client = TestClient(app, raise_server_exceptions=False)
    yield ns
    app.dependency_overrides.clear()
