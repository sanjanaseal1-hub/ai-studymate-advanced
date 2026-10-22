"""Persistent vector store: persistence across restart, filtering, deletion, user separation."""
import pytest
from chromadb.api.shared_system_client import SharedSystemClient

from services.chunking_service import Chunk
from services.vector_store import VectorStore
from tests.helpers import fake_vector

NOW = "2026-01-01T00:00:00+00:00"


def chunk(doc, idx, text, page=None, heading=None):
    return Chunk(f"{doc}:{idx}", doc, f"{doc}.pdf", "pdf", page, heading, idx, text)


def add(store, doc, texts, user="default", **kw):
    chunks = [chunk(doc, i, t, **kw) for i, t in enumerate(texts)]
    store.upsert_chunks(chunks, [fake_vector(t) for t in texts], user, NOW, NOW, "fake")


@pytest.fixture
def store(tmp_path):
    return VectorStore(tmp_path / "chroma", "test")


def test_search_returns_most_similar_chunk_with_metadata(store):
    add(store, "bio", ["DNA replication uses helicase", "Cells divide by mitosis"], page=3, heading="Genetics > DNA")
    add(store, "cook", ["Sourdough needs flour and salt"])
    hits = store.search(fake_vector("DNA replication helicase"), 3, "default")
    assert hits[0].chunk.text.startswith("DNA replication") and hits[0].score > 0.8
    assert (hits[0].chunk.page, hits[0].chunk.heading, hits[0].chunk.filename) == (3, "Genetics > DNA", "bio.pdf")
    assert hits[0].score > hits[-1].score and len(hits) == 3


def test_data_persists_after_restart(tmp_path):
    first = VectorStore(tmp_path / "chroma", "test")
    add(first, "bio", ["DNA replication uses helicase"])
    del first
    SharedSystemClient.clear_system_cache()                     # simulate a fresh process
    second = VectorStore(tmp_path / "chroma", "test")
    assert second.stats("default") == (1, 1)
    assert second.search(fake_vector("helicase"), 1, "default")[0].chunk.document_id == "bio"


def test_adding_documents_keeps_old_ones_and_delete_removes_only_that_document(store):
    add(store, "a", ["alpha text one", "alpha text two"])
    add(store, "b", ["bravo text"])
    assert store.stats("default") == (2, 3)
    store.delete_document("a", "default")
    assert store.stats("default") == (1, 1)
    assert {h.chunk.document_id for h in store.search(fake_vector("alpha bravo text"), 5, "default")} == {"b"}


def test_upsert_same_chunk_ids_does_not_duplicate(store):
    add(store, "a", ["alpha text one", "alpha text two"])
    add(store, "a", ["alpha text one", "alpha text two"])
    assert store.stats("default") == (1, 2)


def test_document_filter_and_user_separation(store):
    add(store, "a", ["shared topic about dna"])
    add(store, "b", ["shared topic about dna"])
    add(store, "c", ["shared topic about dna"], user="other")
    q = fake_vector("topic dna")
    assert {h.chunk.document_id for h in store.search(q, 10, "default")} == {"a", "b"}
    assert [h.chunk.document_id for h in store.search(q, 10, "default", ["b"])] == ["b"]
    assert [h.chunk.document_id for h in store.search(q, 10, "other")] == ["c"]
    assert store.search(q, 10, "nobody") == []
