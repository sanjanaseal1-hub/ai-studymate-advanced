"""Document endpoints: upload (queues background indexing), status, list, re-index/retry, delete."""
import hashlib
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from models.schemas import (DeleteResponse, DocumentInfo, DocumentListResponse, DocumentResponse, FileError,
                            UploadResponse)
from routes.deps import get_user_id
from services import document_repository as repo_mod
from services import ingestion_service
from services.document_repository import DocumentRecord, DocumentRepository, get_document_repository
from services.embedding_service import EmbeddingClient, get_embedding_client
from services.extraction_service import validate_upload
from services.vector_store import VectorStore, get_vector_store
from utils import config
from utils.errors import DocumentError

router = APIRouter(prefix="/api/documents")


def to_info(d: DocumentRecord, duplicate: bool = False) -> DocumentInfo:
    return DocumentInfo(id=d.id, filename=d.filename, file_type=d.file_type, size_bytes=d.size_bytes, status=d.status,
                        error=d.error, pages=d.pages, chunks=d.chunk_count, characters=d.characters,
                        created_at=d.created_at, indexed_at=d.indexed_at, duplicate=duplicate)


def _get_or_404(repo: DocumentRepository, doc_id: str, user_id: str) -> DocumentRecord:
    record = repo.get(doc_id, user_id)
    if record is None:
        raise DocumentError(404, "That document was not found. It may already have been removed.")
    return record


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload(background_tasks: BackgroundTasks, files: list[UploadFile] = File(default=None),
                 auto_index: Optional[str] = Form(None),  # absent or anything but false/0/no/off = index automatically
                  user_id: str = Depends(get_user_id),
                 repo: DocumentRepository = Depends(get_document_repository),
                 store: VectorStore = Depends(get_vector_store),
                 embedder: EmbeddingClient = Depends(get_embedding_client)):
    """Validate + store files and queue them for background indexing. Returns 202 immediately."""
    if not files:
        raise DocumentError(400, "Please choose at least one .pdf, .txt or .md file to upload.")
    if len(files) > config.get_max_files_per_upload():
        raise DocumentError(422, f"You can upload up to {config.get_max_files_per_upload()} files at a time.")
    limit = config.get_max_upload_bytes()
    accepted: list[DocumentInfo] = []
    errors: list[FileError] = []
    to_queue: list[str] = []
    first_status = 422
    for f in files:
        name = f.filename or "unnamed file"
        try:
            data = await f.read(limit + 1)
            file_type = validate_upload(name, data, limit)
            existing = repo.find_by_hash(user_id, hashlib.sha256(data).hexdigest())
            if existing and existing.status != repo_mod.FAILED:   # same content already stored: don't index twice
                accepted.append(to_info(existing, duplicate=True))
                continue
            record = existing or repo.create(user_id, name, file_type, data)
            repo.update(record.id, status=repo_mod.QUEUED, error=None)
            to_queue.append(record.id)
            accepted.append(to_info(repo.get(record.id, user_id)))
        except DocumentError as exc:
            first_status = exc.status_code if not errors else first_status
            errors.append(FileError(filename=name, error=exc.user_message))
    if not accepted:
        raise DocumentError(first_status, " ".join(e.error for e in errors))
    if (auto_index or "true").strip().lower() not in ("false", "0", "no", "off") and to_queue:
        background_tasks.add_task(ingestion_service.process_many, to_queue, user_id, repo, store, embedder)
    return UploadResponse(documents=accepted, errors=errors)


@router.post("/{document_id}/index", response_model=DocumentResponse, status_code=202)
async def index_document(document_id: str, background_tasks: BackgroundTasks, force: bool = False,
                         user_id: str = Depends(get_user_id), repo: DocumentRepository = Depends(get_document_repository),
                         store: VectorStore = Depends(get_vector_store),
                         embedder: EmbeddingClient = Depends(get_embedding_client)):
    """Start (or retry) indexing. Safe to repeat: old chunks are replaced, never duplicated."""
    record = _get_or_404(repo, document_id, user_id)
    if record.status == repo_mod.PROCESSING:
        raise DocumentError(409, "This document is already being processed.")
    if record.status == repo_mod.INDEXED and not force:
        raise DocumentError(409, "This document is already indexed. Use force=true to re-index it.")
    repo.update(document_id, status=repo_mod.QUEUED, error=None)
    background_tasks.add_task(ingestion_service.process_document, document_id, user_id, repo, store, embedder)
    return DocumentResponse(document=to_info(repo.get(document_id, user_id)), message="Indexing started.")


@router.get("", response_model=DocumentListResponse)
async def list_documents(user_id: str = Depends(get_user_id), repo: DocumentRepository = Depends(get_document_repository)):
    return DocumentListResponse(documents=[to_info(d) for d in repo.list(user_id)])


@router.get("/{document_id}", response_model=DocumentResponse)
async def document_status(document_id: str, user_id: str = Depends(get_user_id),
                          repo: DocumentRepository = Depends(get_document_repository)):
    return DocumentResponse(document=to_info(_get_or_404(repo, document_id, user_id)))


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete_document(document_id: str, user_id: str = Depends(get_user_id),
                          repo: DocumentRepository = Depends(get_document_repository),
                          store: VectorStore = Depends(get_vector_store)):
    record = _get_or_404(repo, document_id, user_id)
    if record.status == repo_mod.PROCESSING:
        raise DocumentError(409, "This document is being processed right now. Please try again in a moment.")
    store.delete_document(document_id, user_id)   # all of its chunks
    repo.delete(document_id)                      # record + stored file
    return DeleteResponse(deleted_id=document_id)
