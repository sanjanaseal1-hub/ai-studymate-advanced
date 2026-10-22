"""Reads settings from environment variables (.env in the project root)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()


def get_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
    return [o.strip() for o in raw.split(",") if o.strip()]


# ---------------- RAG settings ----------------
def _env_number(name: str, default, cast):
    try:
        return cast(os.getenv(name, default))
    except (TypeError, ValueError):
        return cast(default)


def get_api_base() -> str:
    return os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")


def get_embedding_model() -> str:
    return os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip()


def get_embedding_dimensions() -> int:
    return _env_number("EMBEDDING_DIMENSIONS", 768, int)


def get_chunk_size() -> int:
    return max(200, _env_number("CHUNK_SIZE", 1000, int))  # characters


def get_chunk_overlap() -> int:
    # Must stay below half the chunk size so the chunker always moves forward.
    return min(max(0, _env_number("CHUNK_OVERLAP", 150, int)), get_chunk_size() // 2 - 1)


def get_top_k() -> int:
    return max(1, _env_number("TOP_K", 4, int))


def get_similarity_threshold() -> float:
    return min(1.0, max(0.0, _env_number("SIMILARITY_THRESHOLD", 0.5, float)))


def get_max_upload_bytes() -> int:
    return int(_env_number("MAX_UPLOAD_MB", 10, float) * 1024 * 1024)


def get_max_files_per_upload() -> int:
    return max(1, _env_number("MAX_FILES_PER_UPLOAD", 5, int))


# ---------------- Advanced RAG settings ----------------
def get_data_dir() -> Path:
    return Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parents[1] / "data")


def get_chroma_dir() -> Path:
    return Path(os.getenv("CHROMA_PATH") or get_data_dir() / "chroma")


def get_collection_name() -> str:
    return os.getenv("CHROMA_COLLECTION", "studymate_chunks").strip()


def get_default_user_id() -> str:
    return os.getenv("DEFAULT_USER_ID", "default").strip()


def get_min_chunk_chars() -> int:
    return max(0, _env_number("MIN_CHUNK_CHARS", 80, int))


def get_candidate_k() -> int:
    return max(get_top_k(), _env_number("CANDIDATE_K", 15, int))  # never fewer candidates than final chunks


def get_rerank_alpha() -> float:
    """Weight of the vector score in the final score (1 - alpha goes to the BM25 score)."""
    return min(1.0, max(0.0, _env_number("RERANK_ALPHA", 0.7, float)))


def get_rag_temperature() -> float:
    return min(1.0, max(0.0, _env_number("RAG_TEMPERATURE", 0.1, float)))


def get_llm_retries() -> int:
    return max(0, _env_number("LLM_MAX_RETRIES", 2, int))


def get_retry_backoff() -> float:
    return max(0.0, _env_number("RETRY_BACKOFF_SECONDS", 1.0, float))
