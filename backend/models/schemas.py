"""Pydantic request models = backend input validation."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_CONTENT_CHARS = 8000
MAX_SHORT_TEXT_CHARS = 100


def _clean_short_text(value: Optional[str]) -> Optional[str]:
    """Trim optional text fields; empty becomes None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


class ContentRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter some study material first.")
        if len(value) > MAX_CONTENT_CHARS:
            raise ValueError(f"Your text is too long. Please keep it under {MAX_CONTENT_CHARS} characters.")
        return value


class SummarizeOptions(BaseModel):
    pass


class QuizOptions(BaseModel):
    num_questions: int = Field(5, ge=1, le=10)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    topic: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_CHARS)

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, value):
        return _clean_short_text(value)


class ExplainOptions(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"] = "beginner"


class ImproveOptions(BaseModel):
    subject: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_CHARS)

    @field_validator("subject")
    @classmethod
    def clean_subject(cls, value):
        return _clean_short_text(value)


class SummarizeRequest(ContentRequest):
    options: SummarizeOptions = Field(default_factory=SummarizeOptions)


class QuizRequest(ContentRequest):
    options: QuizOptions = Field(default_factory=QuizOptions)


class ExplainRequest(ContentRequest):
    options: ExplainOptions = Field(default_factory=ExplainOptions)


class ImproveRequest(ContentRequest):
    options: ImproveOptions = Field(default_factory=ImproveOptions)


class SuccessResponse(BaseModel):
    success: bool = True
    result: str


# ---------------- Document Q&A (advanced RAG) ----------------
import re as _re

MAX_QUESTION_CHARS = 1000
_ID = _re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class QARequest(BaseModel):
    question: str
    document_ids: Optional[list[str]] = Field(None, max_length=20)  # search only these documents

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter a question first.")
        if len(value) > MAX_QUESTION_CHARS:
            raise ValueError(f"Your question is too long. Please keep it under {MAX_QUESTION_CHARS} characters.")
        return value

    @field_validator("document_ids")
    @classmethod
    def validate_ids(cls, value):
        if not value:
            return None
        if any(not _ID.match(v) for v in value):
            raise ValueError("One of the selected documents is invalid.")
        return list(dict.fromkeys(value))


class DocumentInfo(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    status: str                 # queued | processing | indexed | failed
    error: Optional[str] = None
    pages: int = 0
    chunks: int = 0
    characters: int = 0
    created_at: str
    indexed_at: Optional[str] = None
    duplicate: bool = False     # upload matched an already-stored identical file


class FileError(BaseModel):
    filename: str
    error: str


class UploadResponse(BaseModel):
    success: bool = True
    documents: list[DocumentInfo]
    errors: list[FileError] = []


class DocumentResponse(BaseModel):
    success: bool = True
    document: DocumentInfo
    message: str = ""


class DocumentListResponse(BaseModel):
    success: bool = True
    documents: list[DocumentInfo]


class DeleteResponse(BaseModel):
    success: bool = True
    deleted_id: str


class SourceModel(BaseModel):
    citation: Optional[int]              # [n] used in the answer; None if the chunk was not sent to the LLM
    rank: int                            # order in this list
    document_id: str
    document: str
    file_type: str
    page: Optional[int] = None           # PDF only
    heading: Optional[str] = None        # Markdown only
    chunk_index: int
    vector_score: float                  # original cosine similarity
    lexical_score: Optional[float] = None  # BM25 (0..1), None if below threshold
    final_score: Optional[float] = None    # hybrid re-rank score, None if below threshold
    status: Literal["used", "excluded", "below_threshold"]
    cited: bool                          # the validated answer actually cites this chunk
    text: str


class Citation(BaseModel):
    number: int
    document_id: str
    document: str
    page: Optional[int] = None
    heading: Optional[str] = None
    chunk_index: int


class Confidence(BaseModel):
    score: float
    label: Literal["high", "medium", "low", "none"]


class RetrievalDiagnostics(BaseModel):
    documents_searched: int
    chunks_searched: int
    candidate_k: int
    top_k: int
    similarity_threshold: float
    rerank_alpha: float
    candidates_retrieved: int
    candidates_above_threshold: int
    chunks_used: int
    filtered_document_ids: Optional[list[str]] = None
    timings_ms: dict[str, int] = {}


class QAResponse(BaseModel):
    success: bool = True
    answer: str
    state: Literal["grounded", "insufficient", "ungrounded", "no_evidence"]
    grounded: bool
    confidence: Confidence
    citations: list[Citation]
    sources: list[SourceModel]
    retrieval_diagnostics: RetrievalDiagnostics
    warnings: list[str] = []


class ReadyResponse(BaseModel):
    success: bool = True
    status: str
    checks: dict[str, bool]
