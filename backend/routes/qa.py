"""Question answering: plain JSON endpoint and a Server-Sent-Events streaming endpoint."""
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from models.schemas import QARequest, QAResponse
from routes.deps import get_user_id
from services import document_repository as repo_mod
from services import rag_service
from services.document_repository import DocumentRepository, get_document_repository
from services.embedding_service import EmbeddingClient, get_embedding_client
from services.llm_client import LLMClient, get_llm_client
from services.vector_store import VectorStore, get_vector_store
from utils.errors import AppError, DocumentError

router = APIRouter(prefix="/api")
logger = logging.getLogger("studymate.qa")


def _check_request(req: QARequest, user_id: str, repo: DocumentRepository, store: VectorStore) -> None:
    for doc_id in req.document_ids or []:
        record = repo.get(doc_id, user_id)
        if record is None:
            raise DocumentError(404, "One of the selected documents was not found.")
        if record.status != repo_mod.INDEXED:
            raise DocumentError(409, f"'{record.filename}' is not indexed yet. Wait until its status is 'indexed'.")
    rag_service.ensure_ready(store, user_id, req.document_ids)


@router.post("/qa", response_model=QAResponse)
async def ask(req: QARequest, user_id: str = Depends(get_user_id), repo: DocumentRepository = Depends(get_document_repository),
              store: VectorStore = Depends(get_vector_store), embedder: EmbeddingClient = Depends(get_embedding_client),
              llm: LLMClient = Depends(get_llm_client)):
    _check_request(req, user_id, repo, store)
    return await rag_service.answer_question(req.question, user_id, req.document_ids, store, embedder, llm)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data))}\n\n"


@router.post("/qa/stream")
async def ask_stream(req: QARequest, request: Request, user_id: str = Depends(get_user_id),
                     repo: DocumentRepository = Depends(get_document_repository), store: VectorStore = Depends(get_vector_store),
                     embedder: EmbeddingClient = Depends(get_embedding_client), llm: LLMClient = Depends(get_llm_client)):
    """SSE stream of: stage events, token events (progressive answer), then one result (or error) event."""
    _check_request(req, user_id, repo, store)  # normal HTTP errors (409/404) before the stream starts

    async def events():
        pipeline = rag_service.run_pipeline(req.question, user_id, req.document_ids, store, embedder, llm, stream=True)
        try:
            async for event in pipeline:
                if await request.is_disconnected():
                    logger.info("client disconnected; cancelling generation")
                    break
                yield _sse(event["event"], event["data"])
        except AppError as exc:
            logger.error("stream failed (%s): %s", exc.status_code, exc.log_detail or exc.user_message)
            yield _sse("error", {"error": exc.user_message, "status": exc.status_code})
        except Exception:
            logger.exception("unexpected streaming error")
            yield _sse("error", {"error": "Something went wrong on our side. Please try again.", "status": 500})
        finally:
            await pipeline.aclose()  # closes the provider stream => stops paying for tokens nobody reads

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
