from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from models.schemas import ReadyResponse
from services.document_repository import DocumentRepository, get_document_repository
from services.vector_store import VectorStore, get_vector_store
from utils import config

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
async def ready(repo: DocumentRepository = Depends(get_document_repository), store: VectorStore = Depends(get_vector_store)):
    """Readiness: database + vector store work, and an API key is configured (never returns the key)."""
    checks = {}
    for name, probe in (("document_db", repo.ping), ("vector_store", store.ping)):
        try:
            checks[name] = bool(probe())
        except Exception:
            checks[name] = False
    checks["llm_api_key_configured"] = bool(config.get_api_key())
    ok = checks["document_db"] and checks["vector_store"]
    body = ReadyResponse(status="ready" if ok else "unavailable", checks=checks)
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())
