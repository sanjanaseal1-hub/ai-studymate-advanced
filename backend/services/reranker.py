"""RETRIEVAL QUALITY: hybrid re-ranking of vector-search candidates.

Vector search finds passages with similar MEANING but can rank a passage that contains the question's exact
terms (names, numbers, acronyms) too low. BM25 is a classic lexical scorer that rewards exact term overlap.
We retrieve a larger candidate set from the vector DB, score each candidate with BM25 against the question,
and combine:   final = alpha * vector_similarity + (1 - alpha) * bm25_normalised
Trade-off: costs a few milliseconds and needs no extra model/download, but BM25 statistics are computed over
the candidate set only (not the whole corpus) and it cannot understand synonyms - that is what the vector
score is for. A cross-encoder would be more accurate but needs a heavier model.
"""
import math
import re
from dataclasses import dataclass

from services.vector_store import SearchHit

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "is", "are", "was", "were", "of", "and", "or", "to", "in", "on", "for", "with", "what",
         "how", "does", "do", "that", "this", "it", "as", "by", "be", "from", "at", "which", "who", "why", "when"}


@dataclass
class RankedHit:
    hit: SearchHit
    vector_score: float
    lexical_score: float   # BM25 normalised to 0..1 across the candidates
    final_score: float


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def bm25_scores(query_tokens: list[str], documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(documents)
    if n == 0 or not query_tokens:
        return [0.0] * n
    avg_len = (sum(len(d) for d in documents) / n) or 1.0
    doc_freq = {t: sum(1 for d in documents if t in d) for t in set(query_tokens)}
    scores = []
    for doc in documents:
        score = 0.0
        for term in set(query_tokens):
            tf = doc.count(term)
            if tf:
                idf = math.log(1 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(doc) / avg_len))
        scores.append(score)
    return scores


def rerank(question: str, hits: list[SearchHit], alpha: float) -> list[RankedHit]:
    """Return hits sorted by final (hybrid) score, best first."""
    if not hits:
        return []
    raw = bm25_scores(tokenize(question), [tokenize(h.chunk.embedding_text) for h in hits])
    top = max(raw) or 1.0
    ranked = []
    for hit, bm25 in zip(hits, raw):
        lexical = bm25 / top
        vector = max(0.0, hit.score)
        ranked.append(RankedHit(hit, hit.score, lexical, alpha * vector + (1 - alpha) * lexical))
    return sorted(ranked, key=lambda r: r.final_score, reverse=True)
