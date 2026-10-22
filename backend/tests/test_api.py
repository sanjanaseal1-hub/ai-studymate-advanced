"""Backend tests. The LLM is replaced by a fake client, so no network/API key is needed."""
import pytest
from fastapi.testclient import TestClient

from main import app
from services.llm_client import LLMClient, extract_text, get_llm_client, map_http_error
from utils.errors import LLMError


class FakeClient(LLMClient):
    def __init__(self, text="fake answer", error=None):
        self.text, self.error, self.last_prompt = text, error, None

    async def generate(self, system_instruction, prompt):
        self.last_prompt = prompt
        if self.error:
            raise self.error
        return self.text


def make_client(fake):
    app.dependency_overrides[get_llm_client] = lambda: fake
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset():
    yield
    app.dependency_overrides.clear()


ENDPOINTS = ["summarize", "quiz", "explain", "improve-answer"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_valid_request(endpoint):
    fake = FakeClient()
    res = make_client(fake).post(f"/api/{endpoint}", json={"content": "Photosynthesis makes glucose."})
    assert res.status_code == 200
    assert res.json() == {"success": True, "result": "fake answer"}
    assert "Photosynthesis makes glucose." in fake.last_prompt  # structured prompt contains the input


@pytest.mark.parametrize("bad", ["", "   \n ", "x" * 8001])
def test_empty_or_too_long_content(bad):
    fake = FakeClient()
    res = make_client(fake).post("/api/summarize", json={"content": bad})
    assert res.status_code == 422 and res.json()["success"] is False
    assert fake.last_prompt is None  # the LLM was never called


def test_missing_content_and_invalid_options():
    c = make_client(FakeClient())
    assert c.post("/api/summarize", json={}).status_code == 422
    assert c.post("/api/quiz", json={"content": "x", "options": {"num_questions": 99}}).status_code == 422
    assert c.post("/api/quiz", json={"content": "x", "options": {"difficulty": "insane"}}).status_code == 422
    assert c.post("/api/explain", json={"content": "x", "options": {"level": "wizard"}}).status_code == 422


def test_quiz_options_reach_the_prompt():
    fake = FakeClient()
    make_client(fake).post("/api/quiz", json={"content": "Cells", "options": {"num_questions": 3, "difficulty": "hard", "topic": "Mitosis"}})
    assert "3 multiple-choice" in fake.last_prompt and "hard" in fake.last_prompt and "Mitosis" in fake.last_prompt


@pytest.mark.parametrize("status", [429, 503, 504, 502])
def test_api_failure_returns_friendly_error(status):
    err = LLMError(status, "Friendly message", "secret technical detail")
    res = make_client(FakeClient(error=err)).post("/api/summarize", json={"content": "notes"})
    assert res.status_code == status
    assert res.json()["success"] is False and res.json()["error"] == "Friendly message"


def test_unexpected_error_hides_details():
    res = make_client(FakeClient(error=RuntimeError("db password=hunter2"))).post("/api/summarize", json={"content": "notes"})
    assert res.status_code == 500
    assert "hunter2" not in res.text and res.json()["success"] is False


@pytest.mark.parametrize("data", [{}, {"candidates": []}, {"candidates": [{}]}, "oops", {"candidates": [{"content": {"parts": [{"text": "  "}]}}]}])
def test_malformed_or_empty_ai_response(data):
    with pytest.raises(LLMError) as exc:
        extract_text(data)
    assert exc.value.status_code == 502


def test_extract_text_ok_and_blocked():
    assert extract_text({"candidates": [{"content": {"parts": [{"text": "Hi "}, {"text": "there"}]}}]}) == "Hi there"
    with pytest.raises(LLMError) as exc:
        extract_text({"promptFeedback": {"blockReason": "SAFETY"}})
    assert exc.value.status_code == 422


def test_http_error_mapping():
    assert map_http_error(400, "API key not valid").status_code == 500  # invalid key
    assert map_http_error(403, "").status_code == 500
    assert map_http_error(429, "").status_code == 429
    assert map_http_error(500, "").status_code == 503
    assert "key" not in map_http_error(400, "API key not valid").user_message.lower()
