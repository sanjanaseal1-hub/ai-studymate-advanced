"""Stage 4 - EMBEDDINGS. Text -> vector. Kept separate from the LLM (generation) client."""
import logging
from abc import ABC, abstractmethod

from services.llm_client import gemini_post
from utils import config
from utils.errors import LLMError

logger = logging.getLogger("studymate.embedding")
BATCH_SIZE = 100  # Gemini batchEmbedContents limit


class EmbeddingClient(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...


class GeminiEmbeddingClient(EmbeddingClient):
    """Uses task types so document chunks and questions are embedded in a way that
    makes a question land near the passages that answer it."""

    def __init__(self, api_key: str, model: str, dimensions: int, timeout: float = 60.0):
        self.api_key, self.model, self.dimensions, self.timeout = api_key, model, dimensions, timeout

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            payload = {"requests": [{
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
                "taskType": task_type,
                "outputDimensionality": self.dimensions,
            } for text in batch]}
            data = await gemini_post(f"models/{self.model}:batchEmbedContents", payload, self.api_key, self.timeout)
            vectors.extend(_parse_embeddings(data, expected=len(batch)))
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


def _parse_embeddings(data: dict, expected: int) -> list[list[float]]:
    try:
        vectors = [item["values"] for item in data["embeddings"]]
        valid = len(vectors) == expected and all(
            vec and all(isinstance(x, (int, float)) for x in vec) for vec in vectors)
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise LLMError(502, "Unable to process the documents right now. Please try again.",
                       f"Malformed embedding response: {str(data)[:200]}")
    return vectors


def get_embedding_client() -> EmbeddingClient:
    """FastAPI dependency (tests replace it with a fake)."""
    return GeminiEmbeddingClient(config.get_api_key(), config.get_embedding_model(), config.get_embedding_dimensions())
