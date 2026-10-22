"""POST-GENERATION VALIDATION: checks the model's answer against the evidence it was given.

What it does (and does not do): it verifies that every cited number refers to a real source, removes
invalid citations, detects the model's own "not enough information" refusal, measures how much of the
answer carries a citation, and derives a heuristic confidence. It does NOT check that a cited passage
really supports the sentence (that would need an entailment model), so it reduces - not removes - the
risk of unsupported answers.
"""
import re
from dataclasses import dataclass, field

from prompts.rag_prompt import NOT_ENOUGH_INFO

CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class ValidationResult:
    answer: str
    cited: list[int]
    invalid: list[int]
    refused: bool
    coverage: float
    grounded: bool
    state: str                       # grounded | insufficient | ungrounded
    warnings: list[str] = field(default_factory=list)


def validate_answer(answer: str, num_sources: int) -> ValidationResult:
    invalid: list[int] = []
    cited: set[int] = set()

    def fix(match: re.Match) -> str:
        numbers = [int(n) for n in re.split(r"\s*,\s*", match.group(1))]
        good = [n for n in numbers if 1 <= n <= num_sources]
        invalid.extend(n for n in numbers if n not in good)
        cited.update(good)
        return f"[{', '.join(map(str, good))}]" if good else ""

    cleaned = CITATION.sub(fix, answer)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned).strip()

    refused = " ".join(NOT_ENOUGH_INFO.lower().split()) in " ".join(cleaned.lower().split())
    sentences = [s for s in SENTENCE.split(cleaned) if len(s.strip()) >= 40]
    coverage = (sum(1 for s in sentences if CITATION.search(s)) / len(sentences)) if sentences else 1.0

    warnings: list[str] = []
    if invalid:
        warnings.append(f"Removed {len(set(invalid))} invalid citation(s) that did not match any retrieved source.")
    if refused:
        state, grounded = "insufficient", False
    elif not cited:
        state, grounded = "ungrounded", False
        warnings.append("The answer contains no valid citations, so it could not be verified against the sources. Treat it with caution.")
    else:
        state, grounded = "grounded", True
        if coverage < 0.5:
            warnings.append("Several statements in the answer have no citation. Check them against the sources.")
    return ValidationResult(cleaned, sorted(cited), sorted(set(invalid)), refused, coverage, grounded, state, warnings)


def compute_confidence(result: ValidationResult, cited_vector_scores: list[float]) -> tuple[float, str]:
    """Heuristic 0..1: mean similarity of the cited chunks, scaled down for weak citation coverage or invalid citations."""
    if not result.grounded or not cited_vector_scores:
        return 0.0, "none"
    score = (sum(cited_vector_scores) / len(cited_vector_scores)) * (0.5 + 0.5 * result.coverage)
    if result.invalid:
        score *= 0.8
    score = round(max(0.0, min(1.0, score)), 3)
    return score, "high" if score >= 0.7 else "medium" if score >= 0.5 else "low"
