"""INGESTION JOB: raw file -> extract -> clean -> chunk -> embed -> store in vector DB.

Idempotent: chunk ids are deterministic and old chunks are deleted before new ones are written, so a retry
or a forced re-index can never create duplicate chunks. Chunks are only written after ALL embeddings
succeeded, so a failure leaves no half-indexed document.
"""
import asyncio
import logging

from services import document_repository as repo_mod
from services.chunking_service import chunk_document, clean_text
from services.document_repository import DocumentRepository
from services.embedding_service import EmbeddingClient
from services.extraction_service import Page, extract_pages
from services.vector_store import VectorStore
from utils import config
from utils.errors import AppError, DocumentError

logger = logging.getLogger("studymate.ingestion")


def _prepare(filename: str, data: bytes, doc_id: str):
    """CPU-bound part (parsing + chunking); run in a worker thread."""
    file_type, raw_pages = extract_pages(filename, data)
    pages = [Page(p.number, clean_text(p.text, repair_wraps=file_type != "md"), p.heading) for p in raw_pages]
    pages = [p for p in pages if p.text]
    if not pages:
        raise DocumentError(422, f"No readable text was found in '{filename}'. Scanned (image-only) PDFs are not supported.")
    chunks = chunk_document(pages, doc_id, filename, file_type, config.get_chunk_size(),
                            config.get_chunk_overlap(), config.get_min_chunk_chars())
    return raw_pages, pages, chunks


async def process_document(doc_id: str, user_id: str, repo: DocumentRepository, store: VectorStore,
                           embedder: EmbeddingClient) -> None:
    record = repo.get(doc_id, user_id)
    if record is None or record.status == repo_mod.PROCESSING:  # gone, or another job already has it
        return
    repo.update(doc_id, status=repo_mod.PROCESSING, error=None)
    logger.info("[job %s] processing %s", doc_id, record.filename)
    try:
        raw_pages, pages, chunks = await asyncio.to_thread(_prepare, record.filename, repo.read_file(doc_id), doc_id)
        vectors = await embedder.embed_documents([c.embedding_text for c in chunks])
        now = repo_mod.utc_now()
        await asyncio.to_thread(store.delete_document, doc_id, user_id)  # makes retries/re-index idempotent
        await asyncio.to_thread(store.upsert_chunks, chunks, vectors, user_id, record.created_at, now,
                                config.get_embedding_model())
        repo.update(doc_id, status=repo_mod.INDEXED, error=None, pages=len(raw_pages), chunk_count=len(chunks),
                    characters=sum(len(p.text) for p in pages), indexed_at=now)
        logger.info("[job %s] indexed %d chunks", doc_id, len(chunks))
    except AppError as exc:
        logger.error("[job %s] failed (%s): %s", doc_id, exc.status_code, exc.log_detail or exc.user_message)
        repo.update(doc_id, status=repo_mod.FAILED, error=exc.user_message)
    except Exception:
        logger.exception("[job %s] unexpected failure", doc_id)
        repo.update(doc_id, status=repo_mod.FAILED, error="Something went wrong while processing this document. Please retry.")


async def process_many(doc_ids: list[str], user_id: str, repo: DocumentRepository, store: VectorStore,
                       embedder: EmbeddingClient) -> None:
    """Process documents one after another so a multi-file upload doesn't stampede the embedding API."""
    for doc_id in doc_ids:
        await process_document(doc_id, user_id, repo, store, embedder)
