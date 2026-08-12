"""Candidate-pair selection.

Never compares every retrieved claim against every other with an LLM call
(O(n^2) LLM cost). Cross-document pairs are scored by cheap deterministic
topic-overlap similarity, filtered to a minimum threshold, and capped to
``settings.conflict_max_candidate_pairs`` — the expensive classification step
only ever sees a small, ranked shortlist.
"""

from __future__ import annotations

from app.config import settings

from .signals import topic_similarity
from .types import Claim, ConflictCandidate


def select_candidates(
    claims: list[Claim], *, min_similarity: float | None = None, max_pairs: int | None = None
) -> list[ConflictCandidate]:
    """``min_similarity``/``max_pairs`` default to the process-wide settings
    but can be overridden per call (Trust Layer Phase 4's MAX_TRUST mode) —
    never by mutating ``settings`` itself, which is a shared singleton across
    concurrent requests."""
    threshold = settings.conflict_candidate_min_similarity if min_similarity is None else min_similarity
    cap = settings.conflict_max_candidate_pairs if max_pairs is None else max_pairs

    pairs: list[ConflictCandidate] = []
    for i, a in enumerate(claims):
        for b in claims[i + 1 :]:
            if a.document_id == b.document_id:
                continue  # same-document claims are detail, never a lineage conflict
            sim = topic_similarity(a.entities, b.entities)
            if sim >= threshold:
                pairs.append(ConflictCandidate(claim_a=a, claim_b=b, similarity=sim))
    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs[:cap]
