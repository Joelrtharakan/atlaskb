"""Obvious-case classification without an LLM call.

Candidate pairs (already topic-filtered by `candidates.select_candidates`)
that assert clearly different numbers or dates are confidently CONTRADICTS;
pairs that assert the same numbers are confidently SUPPORTS. Everything else
(no numbers/dates, overlapping-but-not-identical number sets, text-only
claims) is left for the LLM classification stage — this function returns
``None`` rather than guessing.

Confidence values are fixed, documented constants
(``settings.conflict_deterministic_*``), not learned or calibrated against a
validation set. This is a heuristic, not a proof: a chunk with several
incidental numbers (e.g. a page reference alongside a policy figure) can
still misfire. See ``eval/conflicts/README.md`` for the benchmark that
quantifies how often that happens.
"""

from __future__ import annotations

from app.config import settings

from .types import ConflictCandidate, Relationship, StructuredConflict


def try_classify(candidate: ConflictCandidate) -> StructuredConflict | None:
    a, b = candidate.claim_a, candidate.claim_b

    if a.numbers and b.numbers:
        a_nums, b_nums = {round(n, 2) for n in a.numbers}, {round(n, 2) for n in b.numbers}
        if a_nums == b_nums:
            return _result(
                candidate,
                Relationship.SUPPORTS,
                settings.conflict_deterministic_agreement_confidence,
                f"Same numeric value(s) stated: {sorted(a_nums)}.",
                topic="Numeric agreement",
            )
        if not (a_nums & b_nums):
            # Disjoint number sets on an already topic-similar pair — the
            # strongest deterministic signal available without an LLM call.
            return _result(
                candidate,
                Relationship.CONTRADICTS,
                settings.conflict_deterministic_numeric_confidence,
                f"Numeric values differ: {sorted(a_nums)} vs {sorted(b_nums)}.",
                topic="Numeric disagreement",
            )
        # Partial overlap (e.g. one claim has an extra incidental number) is
        # genuinely ambiguous — defer to the LLM rather than guess.

    if a.dates and b.dates:
        a_dates, b_dates = set(a.dates), set(b.dates)
        if a_dates and b_dates and not (a_dates & b_dates):
            return _result(
                candidate,
                Relationship.CONTRADICTS,
                settings.conflict_deterministic_date_confidence,
                f"Dates differ: {sorted(a_dates)} vs {sorted(b_dates)}.",
                topic="Date disagreement",
            )

    return None  # no confident deterministic signal -> defer to the LLM stage


def _result(
    candidate: ConflictCandidate,
    relationship: Relationship,
    confidence: float,
    explanation: str,
    *,
    topic: str,
) -> StructuredConflict:
    a, b = candidate.claim_a, candidate.claim_b
    return StructuredConflict(
        topic=topic,
        document_id_a=a.document_id,
        document_version_a=a.version_id,
        chunk_id_a=a.chunk_id,
        claim_a=a.text,
        document_id_b=b.document_id,
        document_version_b=b.version_id,
        chunk_id_b=b.chunk_id,
        claim_b=b.text,
        relationship=relationship,
        confidence=confidence,
        explanation=explanation,
        method="deterministic",
    )
