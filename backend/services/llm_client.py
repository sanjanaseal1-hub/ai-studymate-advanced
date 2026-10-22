"""LLM provider layer.

Routes/services only know `LLMClient`. To switch provider, write another subclass and change
`get_llm_client`. Providers without streaming inherit a `stream()` that yields one chunk.
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from utils import config
from utils.errors import LLMError

logger = logging.getLogger("studymate.llm")
GENERIC_FAIL = "Unable to generate the response right now. Please try again."
NOT_CONFIGURED = "The AI service is not configured correctly. Please contact the administrator."


class LLMClient(ABC):
    @abstractmethod
    async def generate(self, system_instruction: str, prompt: str, temperature: Optional[float] = None) -> str:
        """Return the model's full text answer or raise LLMError."""

    async def stream(self, system_instruction: str, prompt: str, temperature: Optional[float] = None) -> AsyncIterator[str]:
        """Yield the answer in pieces. Default: no real streaming, one piece."""
        yield await self.generate(system_instruction, prompt, temperature)


def map_http_error(status: int, body: str) -> LLMError:
    """Turn a provider HTTP error into a safe, user-friendly LLMError."""
    detail = f"Gemini returned HTTP {status}: {body[:300]}"
    if status in (401, 403) or (status == 400 and "API key" in body):
        return LLMError(500, NOT_CONFIGURED, detail)
    if status == 429:
        return LLMError(429, "Too many requests right now. Please wait a moment and try again.", detail, retryable=True)
    if status >= 500:
        return LLMError(503, "The AI service is temporarily unavailable. Please try again later.", detail, retryable=True)
    return LLMError(502, GENERIC_FAIL, detail)


def extract_text(data: dict) -> str:
    """Pull the answer text out of Gemini's JSON, validating its shape."""
    if not isinstance(data, dict):
        raise LLMError(502, GENERIC_FAIL, "Response is not a JSON object")
    block = data.get("promptFeedback", {}).get("blockReason")
    if block:
        raise LLMError(422, "The AI could not process this content. Please try different study material.", f"Blocked: {block}")
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise LLMError(502, GENERIC_FAIL, f"Malformed response: {str(data)[:300]}")
    if not text:
        raise LLMError(502, "The AI returned an empty response. Please try again.", "Empty text in response")
    return text


async def _post_once(path: str, payload: dict, api_key: str, timeout: float) -> dict:
    if not api_key:
        raise LLMError(500, NOT_CONFIGURED, "GEMINI_API_KEY is missing")
    headers = {"x-goog-api-key": api_key}  # header, not URL: the key never shows up in logs
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{config.get_api_base()}/{path}", json=payload, headers=headers)
    except httpx.TimeoutException:
        raise LLMError(504, "The AI took too long to respond. Please try again.", "Gemini request timed out", retryable=True)
    except httpx.RequestError as exc:
        raise LLMError(502, "Could not reach the AI service. Please check the connection and try again.",
                       f"Network error: {type(exc).__name__}", retryable=True)
    if response.status_code != 200:
        raise map_http_error(response.status_code, response.text)
    try:
        return response.json()
    except ValueError:
        raise LLMError(502, GENERIC_FAIL, "Invalid JSON from Gemini")


async def gemini_post(path: str, payload: dict, api_key: str, timeout: float) -> dict:
    """POST to Gemini with retry + exponential backoff for transient failures (429, 5xx, timeout, network)."""
    retries = config.get_llm_retries()
    for attempt in range(retries + 1):
        try:
            return await _post_once(path, payload, api_key, timeout)
        except LLMError as exc:
            if not exc.retryable or attempt >= retries:
                raise
            delay = config.get_retry_backoff() * (2 ** attempt)
            logger.warning("Gemini call failed (%s); retry %d/%d in %.1fs", exc.status_code, attempt + 1, retries, delay)
            await asyncio.sleep(delay)
    raise LLMError(502, GENERIC_FAIL)  # unreachable, keeps type checkers happy


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str, timeout: float = 45.0, temperature: float = 0.4):
        self.api_key, self.model, self.timeout, self.temperature = api_key, model, timeout, temperature

    def _payload(self, system_instruction: str, prompt: str, temperature: Optional[float]) -> dict:
        return {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature if temperature is None else temperature,
                                 "maxOutputTokens": 2048},
        }

    async def generate(self, system_instruction: str, prompt: str, temperature: Optional[float] = None) -> str:
        data = await gemini_post(f"models/{self.model}:generateContent",
                                 self._payload(system_instruction, prompt, temperature), self.api_key, self.timeout)
        return extract_text(data)

    async def stream(self, system_instruction: str, prompt: str, temperature: Optional[float] = None) -> AsyncIterator[str]:
        """Real token streaming through Gemini's Server-Sent-Events endpoint."""
        if not self.api_key:
            raise LLMError(500, NOT_CONFIGURED, "GEMINI_API_KEY is missing")
        url = f"{config.get_api_base()}/models/{self.model}:streamGenerateContent?alt=sse"
        produced = False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=self._payload(system_instruction, prompt, temperature),
                                         headers={"x-goog-api-key": self.api_key}) as response:
                    if response.status_code != 200:
                        raise map_http_error(response.status_code, (await response.aread()).decode(errors="replace"))
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            data = json.loads(line[5:].strip())
                        except ValueError:
                            continue  # ignore keep-alives / partial lines
                        if data.get("promptFeedback", {}).get("blockReason"):
                            raise LLMError(422, "The AI could not process this content.", f"Blocked: {data['promptFeedback']}")
                        for candidate in data.get("candidates", []):
                            for part in candidate.get("content", {}).get("parts", []):
                                if part.get("text") and not part.get("thought"):
                                    produced = True
                                    yield part["text"]
        except httpx.TimeoutException:
            raise LLMError(504, "The AI took too long to respond. Please try again.", "Gemini stream timed out")
        except httpx.RequestError as exc:
            raise LLMError(502, "Could not reach the AI service. Please check the connection and try again.",
                           f"Network error: {type(exc).__name__}")
        if not produced:
            raise LLMError(502, "The AI returned an empty response. Please try again.", "Empty stream")


def get_llm_client() -> LLMClient:
    """FastAPI dependency (tests replace it with a fake client)."""
    return GeminiClient(config.get_api_key(), config.get_model())
