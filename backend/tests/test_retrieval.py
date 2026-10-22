"""Re-ranking and citation validation (pure logic, no app)."""
from prompts.rag_prompt import NOT_ENOUGH_INFO
from services.answer_validation import compute_confidence, validate_answer
from services.chunking_service import Chunk
from services.reranker import bm25_scores, rerank, tokenize
from services.vector_store import SearchHit


def hit(idx, text, score, heading=None):
    return SearchHit(Chunk(f"d:{idx}", "d", "d.txt", "txt", None, heading, idx, text), score)


def test_bm25_rewards_exact_term_overlap():
    docs = [tokenize("the mitochondria produces energy"), tokenize("ribosomes make protein"), tokenize("unrelated words here")]
    scores = bm25_scores(tokenize("mitochondria energy"), docs)
    assert scores[0] > scores[1] and scores[0] > scores[2] and scores[2] == 0


def test_rerank_promotes_exact_match_over_slightly_higher_vector_score():
    vague = hit(0, "General discussion about cell biology and organelles.", 0.62)
    exact = hit(1, "Error code E4021 means the pump pressure sensor failed.", 0.58)
    ranked = rerank("What does error code E4021 mean?", [vague, exact], alpha=0.7)
    assert [r.hit.chunk.chunk_index for r in ranked] == [1, 0]           # re-ranked: exact match moved to the top
    assert ranked[0].vector_score == 0.58 and ranked[0].lexical_score == 1.0
    assert ranked[0].final_score > ranked[1].final_score


def test_alpha_one_keeps_pure_vector_order_and_scores_are_exposed():
    a, b = hit(0, "alpha beta", 0.9), hit(1, "gamma delta epsilon", 0.4)
    ranked = rerank("gamma delta", [a, b], alpha=1.0)
    assert [r.hit.chunk.chunk_index for r in ranked] == [0, 1]
    assert all(0 <= r.lexical_score <= 1 and r.final_score == r.vector_score for r in ranked)
    assert rerank("x", [], 0.7) == []


def test_heading_text_participates_in_lexical_score():
    plain = hit(0, "It lets the cell copy material.", 0.6)
    titled = hit(1, "It lets the cell copy material.", 0.6, heading="DNA Replication")
    assert rerank("DNA replication", [plain, titled], 0.5)[0].hit.chunk.chunk_index == 1


# ---------- citation validation ----------
def test_valid_citations_are_kept_and_grounded():
    r = validate_answer("DNA is copied by polymerase [1]. Helicase unwinds the helix [2][1].", num_sources=2)
    assert r.cited == [1, 2] and r.invalid == [] and r.grounded and r.state == "grounded" and r.warnings == []


def test_invalid_citations_are_removed_and_flagged():
    r = validate_answer("Polymerase builds strands [1]. Helicase is also involved [7].", num_sources=2)
    assert "[7]" not in r.answer and "[1]" in r.answer and r.invalid == [7]
    assert any("invalid citation" in w for w in r.warnings) and r.grounded


def test_mixed_citation_group_keeps_only_valid_numbers():
    r = validate_answer("Both agree on this point about replication in cells [1, 9].", num_sources=3)
    assert "[1]" in r.answer and "9" not in r.answer and r.cited == [1]


def test_answer_without_citations_is_flagged_ungrounded():
    r = validate_answer("DNA replication is semi-conservative and happens in the S phase of the cell cycle.", 3)
    assert not r.grounded and r.state == "ungrounded" and r.warnings


def test_refusal_is_detected_as_insufficient():
    r = validate_answer(NOT_ENOUGH_INFO, 3)
    assert r.refused and r.state == "insufficient" and not r.grounded


def test_low_citation_coverage_warns_and_confidence_is_heuristic():
    text = ("This first statement is long enough to count as a sentence on its own. "
            "This second statement is also long enough to count as a sentence. "
            "This third statement likewise has no citation attached at all. Final cited claim here, long enough to count [1].")
    r = validate_answer(text, 2)
    assert r.coverage < 0.5 and any("no citation" in w for w in r.warnings)
    full = validate_answer("A fully cited and sufficiently long statement about replication [1].", 2)
    high, label_high = compute_confidence(full, [0.9])
    low, label_low = compute_confidence(r, [0.9])
    assert high > low and label_high == "high" and compute_confidence(validate_answer(NOT_ENOUGH_INFO, 1), [0.9]) == (0.0, "none")
