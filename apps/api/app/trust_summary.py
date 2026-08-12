"""Explainable Trust Summary (Trust Layer Phase 5).

Replaces a meaningless "Trust: 100%" with structured, evidence-derived
signals — every field here traces to a real value already computed
elsewhere in the response (citations, evidence, conflicts). Nothing here is
invented: a question with weak grounding must read as weak, not be smoothed
into a falsely reassuring summary (execution rule: "never claim certainty
when evidence is incomplete", "do not claim '100% trustworthy'").

``citation_coverage`` reuses the exact sentence-to-claim substring-overlap
algorithm ``eval/run_before_after.py::citation_coverage()`` already uses
offline, so the number a user sees live and the number this project's own
eval reports for the same answer are the same computation, not two
divergent implementations that could quietly disagree.
"""

from __future__ import annotations

import re

from app.schemas import Citation, Conflict, Evidence, TrustSummary

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")


def citation_coverage(answer: str, citations: list[Citation]) -> float | None:
    """Fraction of the answer's sentences matched by at least one citation's
    claim text (case-insensitive substring overlap, either direction).
    ``None`` if the answer has no sentences to grade (e.g. empty)."""
    sentences = [s.strip() for s in _SENTENCE_RE.findall(answer) if s.strip()]
    if not sentences:
        return None
    claims = [c.claim.strip().lower() for c in citations if c.claim.strip()]
    if not claims:
        return 0.0
    covered = 0
    for sentence in sentences:
        s = sentence.lower()
        if any(claim in s or s in claim for claim in claims):
            covered += 1
    return round(covered / len(sentences), 3)


# Fixed, documented thresholds — a judgment call informed by this project's
# own measured baselines (README's "Measured results": full-system citation
# coverage has run 75-92% in this project's real evals), not independently
# calibrated against a labeled quality dataset. Treat "High"/"Medium"/"Low"
# as a readable bucketing of the real number, not a separately-verified
# quality score — the underlying float is always available too.
_COVERAGE_HIGH = 0.8
_COVERAGE_MEDIUM = 0.5
_STALENESS_HIGH_FRESH = 0.33  # avg staleness below this -> "High" freshness
_STALENESS_MEDIUM_FRESH = 0.66


def _bucket(value: float, *, high: float, medium: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        if value >= high:
            return "High"
        if value >= medium:
            return "Medium"
        return "Low"
    if value <= high:
        return "High"
    if value <= medium:
        return "Medium"
    return "Low"


def build_trust_summary(
    *,
    answerable: bool,
    answer: str,
    citations: list[Citation],
    evidence: list[Evidence],
    conflicts: list[Conflict],
) -> TrustSummary | None:
    """``None`` for a refusal — there are no claims to summarize trust for.
    For an answerable response, every field is derived from real data; a
    thin answer (few/no citations, no evidence) reads as thin, not as a
    default-high score."""
    if not answerable:
        return None

    coverage = citation_coverage(answer, citations)
    if coverage is None:
        citation_quality = "Unknown"
    else:
        citation_quality = _bucket(coverage, high=_COVERAGE_HIGH, medium=_COVERAGE_MEDIUM)

    if not evidence:
        source_freshness = "Unknown"
        version = "Unknown"
        evidence_completeness = "Low"
    else:
        avg_staleness = sum(e.staleness for e in evidence) / len(evidence)
        source_freshness = _bucket(
            avg_staleness, high=_STALENESS_HIGH_FRESH, medium=_STALENESS_MEDIUM_FRESH,
            higher_is_better=False,
        )
        current_flags = {e.is_current_version for e in evidence}
        if current_flags == {True}:
            version = "Current"
        elif current_flags == {False}:
            version = "Historical"
        else:
            version = "Mixed"
        scored = sum(
            1 for e in evidence if e.dense_score is not None or e.sparse_score is not None
            or e.rerank_score is not None
        )
        completeness_ratio = scored / len(evidence)
        evidence_completeness = _bucket(completeness_ratio, high=0.99, medium=0.5)

    contradicts = [c for c in conflicts if c.relationship == "CONTRADICTS"]
    conflicts_summary = (
        "None detected"
        if not contradicts
        else f"{len(contradicts)} conflict(s) detected: " + "; ".join(c.topic for c in contradicts[:3])
    )

    return TrustSummary(
        citation_coverage=coverage,
        citation_quality=citation_quality,
        source_freshness=source_freshness,
        version=version,
        conflicts_detected=len(contradicts),
        conflicts_summary=conflicts_summary,
        evidence_completeness=evidence_completeness,
        # Retrieval is RBAC/ACL-scoped at the query level (document_visible_clause,
        # the single choke point every retrieval path goes through) — every
        # chunk that reached this answer was already permission-filtered
        # before generation ever ran. This reports that structural guarantee,
        # not a separate redundant re-check invented for this summary.
        permission_check="Passed",
    )
