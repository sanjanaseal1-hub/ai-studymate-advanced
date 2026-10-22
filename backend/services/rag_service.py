"""QUESTION ANSWERING PIPELINE (async generator that yields progress events).

question -> embed -> vector search (candidate_k) -> relevance threshold -> hybrid re-rank -> top_k
         -> numbered context -> LLM (grounded prompt, low temperature) -> citation validation -> result

Events: {"event": "stage"|"token"|"result", "data": ...}. The SSE endpoint forwards them; the plain
endpoint just returns the final result. If the client disconnects, the generator is closed and the
provider stream is cancelled.
"""
import asyncio
import logging
import time
from typing import AsyncIterator, Optional

from models.schemas import Citation, Confidence, QAResponse, RetrievalDiagnostics, SourceModel
from prompts.rag_prompt import NO_RELEVANT_MESSAGE, RAG_SYSTEM_ROLE, build_context, build_rag_prompt
from services.answer_validation import compute_confidence, validate_answer
from services.embedding_service import EmbeddingClient
from services.llm_client import LLMClient
from services.reranker import RankedHit, rerank
from services.vector_store import VectorStore
from utils import config
from utils.errors import DocumentError

logger = logging.getLogger("studymate.rag")


def ensure_ready(store: VectorStore, user_id: str, document_ids: Optional[list[str]]) -> None:
    if store.stats(user_id, document_ids)[1] == 0:
        raise DocumentError(409, "No indexed documents are available to search. Upload a document and wait until it is indexed.")


def _stage(name: str, message: str) -> dict:
    return {"event": "stage", "data": {"stage": name, "message": message}}


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def run_pipeline(question: str, user_id: str, document_ids: Optional[list[str]], store: VectorStore,
                       embedder: EmbeddingClient, llm: LLMClient, stream: bool) -> AsyncIterator[dict]:
    candidate_k, top_k = config.get_candidate_k(), config.get_top_k()
    threshold, alpha = config.get_similarity_threshold(), config.get_rerank_alpha()
    timings: dict[str, int] = {}

    yield _stage("embedding", "Embedding your question…")
    t = time.perf_counter()
    query_vector = await embedder.embed_query(question)
    timings["embedding"] = _ms(t)

    t = time.perf_counter()
    docs_searched, chunks_searched = await asyncio.to_thread(store.stats, user_id, document_ids)
    yield _stage("retrieving", f"Searching {chunks_searched} chunks in {docs_searched} document(s)…")
    candidates = await asyncio.to_thread(store.search, query_vector, candidate_k, user_id, document_ids)
    timings["retrieval"] = _ms(t)

    t = time.perf_counter()
    above = [h for h in candidates if h.score >= threshold]               # relevance gate on the semantic score
    yield _stage("reranking", f"Re-ranking {len(above)} candidate chunk(s)…")
    ranked = rerank(question, above, alpha)
    final, excluded = ranked[:top_k], ranked[top_k:]
    below = [h for h in candidates if h.score < threshold]
    timings["reranking"] = _ms(t)
    logger.info("retrieved=%d above_threshold=%d used=%d best=%.3f", len(candidates), len(above), len(final),
                candidates[0].score if candidates else 0)

    def make_source(rank_no: int, ranked_hit, status: str, citation: Optional[int] = None) -> SourceModel:
        c = ranked_hit.hit.chunk
        return SourceModel(citation=citation, rank=rank_no, document_id=c.document_id, document=c.filename,
                           file_type=c.file_type, page=c.page, heading=c.heading, chunk_index=c.chunk_index,
                           vector_score=round(ranked_hit.vector_score, 4),
                           lexical_score=None if status == "below_threshold" else round(ranked_hit.lexical_score, 4),
                           final_score=None if status == "below_threshold" else round(ranked_hit.final_score, 4),
                           status=status, cited=False, text=c.text)

    sources = [make_source(i, r, "used", citation=i) for i, r in enumerate(final, start=1)]
    sources += [make_source(len(sources) + i, r, "excluded") for i, r in enumerate(excluded, start=1)]
    below_ranked = [RankedHit(h, h.score, 0.0, 0.0) for h in below]  # not re-ranked; shown for transparency
    sources += [make_source(len(sources) + i, r, "below_threshold") for i, r in enumerate(below_ranked, start=1)]

    def diagnostics() -> RetrievalDiagnostics:
        return RetrievalDiagnostics(documents_searched=docs_searched, chunks_searched=chunks_searched,
                                    candidate_k=candidate_k, top_k=top_k, similarity_threshold=threshold,
                                    rerank_alpha=alpha, candidates_retrieved=len(candidates),
                                    candidates_above_threshold=len(above), chunks_used=len(final),
                                    filtered_document_ids=document_ids, timings_ms=timings)

    if not final:  # nothing relevant enough: do NOT call the LLM
        yield {"event": "result", "data": QAResponse(
            answer=NO_RELEVANT_MESSAGE, state="no_evidence", grounded=False, confidence=Confidence(score=0, label="none"),
            citations=[], sources=sources, retrieval_diagnostics=diagnostics(),
            warnings=["No retrieved chunk reached the similarity threshold, so the AI was not asked to answer."])}
        return

    yield _stage("generating", f"Generating a grounded answer from {len(final)} source(s)…")
    t = time.perf_counter()
    prompt = build_rag_prompt(question, build_context(final))
    temperature = config.get_rag_temperature()
    pieces: list[str] = []
    if stream:
        async for piece in llm.stream(RAG_SYSTEM_ROLE, prompt, temperature):
            pieces.append(piece)
            yield {"event": "token", "data": {"text": piece}}
    else:
        pieces.append(await llm.generate(RAG_SYSTEM_ROLE, prompt, temperature))
    timings["generation"] = _ms(t)

    yield _stage("validating", "Validating citations…")
    check = validate_answer("".join(pieces).strip(), len(final))
    for source in sources:
        source.cited = source.citation in check.cited
    score, label = compute_confidence(check, [final[n - 1].vector_score for n in check.cited])
    citations = [Citation(number=n, document_id=s.document_id, document=s.document, page=s.page,
                          heading=s.heading, chunk_index=s.chunk_index)
                 for n in check.cited for s in [sources[n - 1]]]
    yield {"event": "result", "data": QAResponse(
        answer=check.answer, state=check.state, grounded=check.grounded, confidence=Confidence(score=score, label=label),
        citations=citations, sources=sources, retrieval_diagnostics=diagnostics(), warnings=check.warnings)}


async def answer_question(question: str, user_id: str, document_ids, store, embedder, llm) -> QAResponse:
    result = None
    async for event in run_pipeline(question, user_id, document_ids, store, embedder, llm, stream=False):
        if event["event"] == "result":
            result = event["data"]
    return result
