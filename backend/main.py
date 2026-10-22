"""AI StudyMate backend entry point.  Run: uvicorn main:app --reload   (docs: /docs)"""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from routes.documents import router as documents_router
from routes.health import router as health_router
from routes.qa import router as qa_router
from routes.study import router as study_router
from services.document_repository import get_document_repository
from services.vector_store import get_vector_store
from utils import config
from utils.errors import AppError
from utils.logging_utils import request_id_var, setup_logging

setup_logging()
logger = logging.getLogger("studymate")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_vector_store()  # open the persistent index at startup so problems show immediately
    interrupted = get_document_repository().recover_interrupted()
    if interrupted:
        logger.warning("Marked %d interrupted indexing job(s) as failed so they can be retried", interrupted)
    yield


app = FastAPI(title="AI StudyMate API", version="3.0", lifespan=lifespan,
              description="Document Q&A (RAG) with persistent vector search, re-ranking, grounded cited answers and SSE streaming, "
                          "plus study utilities.")
app.add_middleware(CORSMiddleware, allow_origins=config.get_allowed_origins(), allow_methods=["POST", "GET", "DELETE"],
                   allow_headers=["Content-Type"], expose_headers=["X-Request-ID"])


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")[:36] or uuid.uuid4().hex[:8]
    request_id_var.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


for router in (health_router, study_router, documents_router, qa_router):
    app.include_router(router)


def _error(status: int, message: str) -> JSONResponse:
    """The single error format used by every endpoint."""
    return JSONResponse(status_code=status, content={"success": False, "error": message, "request_id": request_id_var.get()})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    err = exc.errors()[0]
    if err["type"] == "missing":
        message = "Please fill in the required fields."
    elif err["type"] == "value_error":
        message = str(err["msg"]).removeprefix("Value error, ")
    else:
        message = "One of the selected options is invalid."
    return _error(422, message)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return _error(exc.status_code, "That page or action was not found." if exc.status_code == 404 else "The request could not be completed.")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error("App error (%s): %s", exc.status_code, exc.log_detail or exc.user_message)  # technical detail stays in the log
    return _error(exc.status_code, exc.user_message)


@app.exception_handler(Exception)
async def unexpected_handler(request: Request, exc: Exception):
    logger.exception("Unexpected error")
    return _error(500, "Something went wrong on our side. Please try again.")
