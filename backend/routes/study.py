"""The four study endpoints. Each: validate -> build prompt -> call LLM -> return result."""
import logging

from fastapi import APIRouter, Depends

from models.schemas import (ExplainRequest, ImproveRequest, QuizRequest,
                            SuccessResponse, SummarizeRequest)
from prompts import templates
from services.llm_client import LLMClient, get_llm_client

router = APIRouter(prefix="/api")
logger = logging.getLogger("studymate.routes")


async def _run(client: LLMClient, prompt: str, feature: str) -> SuccessResponse:
    logger.info("Generating: %s", feature)
    text = await client.generate(templates.SYSTEM_ROLE, prompt)
    return SuccessResponse(result=text)


@router.post("/summarize", response_model=SuccessResponse)
async def summarize(req: SummarizeRequest, client: LLMClient = Depends(get_llm_client)):
    return await _run(client, templates.build_summarize_prompt(req.content, req.options), "summarize")


@router.post("/quiz", response_model=SuccessResponse)
async def quiz(req: QuizRequest, client: LLMClient = Depends(get_llm_client)):
    return await _run(client, templates.build_quiz_prompt(req.content, req.options), "quiz")


@router.post("/explain", response_model=SuccessResponse)
async def explain(req: ExplainRequest, client: LLMClient = Depends(get_llm_client)):
    return await _run(client, templates.build_explain_prompt(req.content, req.options), "explain")


@router.post("/improve-answer", response_model=SuccessResponse)
async def improve_answer(req: ImproveRequest, client: LLMClient = Depends(get_llm_client)):
    return await _run(client, templates.build_improve_prompt(req.content, req.options), "improve-answer")
