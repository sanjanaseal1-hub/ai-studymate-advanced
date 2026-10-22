"""STAGE 5 - PERSISTENT VECTOR STORE (ChromaDB).

Why Chroma: free, embedded (no server), persists to disk, HNSW approximate nearest-neighbour index with
cosine distance, metadata filtering. Data lives in CHROMA_PATH, which Docker mounts as a volume.

Embeddings are computed by OUR embedding client and passed in explicitly (embedding_function=None), so
Chroma never downloads a model. Every chunk carries `user_id` + `document_id` metadata, which is what
makes per-user separation and per-document filtering possible.
"""
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import chromadb
from chromadb.config import Settings

from services.chunking_service import Chunk
from utils import config
from utils.errors import DocumentError

logger = logging.getLogger("studymate.vectorstore")
UPSERT_BATCH = 500


@dataclass
class SearchHit:
    chunk: Chunk
    score: float  # cosine similarity (1 - cosine distance); higher = more similar


class VectorStore:
    def __init__(self, path, collection: str = "studymate_chunks") -> None:
        self.client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}, embedding_function=None)

    @staticmethod
    def _where(user_id: str, document_ids: Optional[list[str]] = None) -> dict:
        conditions: list[dict] = [{"user_id": user_id}]
        if document_ids:
            conditions.append({"document_id": {"$in": list(document_ids)}})
        return conditions[0] if len(conditions) == 1 else {"$and": conditions}

    def upsert_chunks(self, chunks: list[Chunk], vectors: list[list[float]], user_id: str,
                      upload_time: str, indexed_at: str, embedding_model: str = "") -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        try:
            for i in range(0, len(chunks), UPSERT_BATCH):
                batch = chunks[i:i + UPSERT_BATCH]
                metadatas = []
                for c in batch:
                    meta = {"document_id": c.document_id, "user_id": user_id, "filename": c.filename,
                            "file_type": c.file_type, "chunk_index": c.chunk_index, "upload_time": upload_time,
                            "indexed_at": indexed_at, "embedding_model": embedding_model}
                    if c.page is not None:
                        meta["page"] = c.page
                    if c.heading:
                        meta["heading"] = c.heading
                    metadatas.append(meta)
                self.collection.upsert(ids=[c.chunk_id for c in batch], embeddings=vectors[i:i + UPSERT_BATCH],
                                       documents=[c.text for c in batch], metadatas=metadatas)
        except (ValueError, chromadb.errors.ChromaError) as exc:
            raise DocumentError(500, "The document index is not compatible with the current embedding settings. "
                                     "Delete the stored data or change CHROMA_COLLECTION.",
                                f"Chroma upsert failed: {type(exc).__name__}: {exc}")

    def delete_document(self, document_id: str, user_id: str) -> None:
        self.collection.delete(where=self._where(user_id, [document_id]))

    def stats(self, user_id: str, document_ids: Optional[list[str]] = None) -> tuple[int, int]:
        """(documents, chunks) matching the filter."""
        metadatas = self.collection.get(where=self._where(user_id, document_ids), include=["metadatas"])["metadatas"]
        return len({m["document_id"] for m in metadatas}), len(metadatas)

    def search(self, query_vector: list[float], n_results: int, user_id: str,
               document_ids: Optional[list[str]] = None) -> list[SearchHit]:
        """Nearest chunks by cosine similarity, optionally restricted to given documents."""
        _, total = self.stats(user_id, document_ids)
        if total == 0:
            return []
        try:
            res = self.collection.query(query_embeddings=[query_vector], n_results=min(n_results, total),
                                        where=self._where(user_id, document_ids),
                                        include=["documents", "metadatas", "distances"])
        except (ValueError, chromadb.errors.ChromaError) as exc:
            raise DocumentError(500, "The document index is not compatible with the current embedding settings.",
                                f"Chroma query failed: {type(exc).__name__}: {exc}")
        hits = []
        for text, meta, distance in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            chunk = Chunk(f"{meta['document_id']}:{meta['chunk_index']}", meta["document_id"], meta["filename"],
                          meta["file_type"], meta.get("page"), meta.get("heading"), meta["chunk_index"], text)
            hits.append(SearchHit(chunk, max(-1.0, min(1.0, 1.0 - float(distance)))))
        return hits

    def ping(self) -> bool:
        self.client.heartbeat()
        return True


@lru_cache
def get_vector_store() -> VectorStore:
    """FastAPI dependency: one shared store (tests override it with a temp-dir store)."""
    return VectorStore(config.get_chroma_dir(), config.get_collection_name())
