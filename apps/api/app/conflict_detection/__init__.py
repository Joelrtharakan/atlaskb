"""Structured conflict-detection pipeline (Trust Layer Phase 1).

Replaces the single whole-context LLM call in ``app.llm.detect_conflicts``
(kept in place, still tested, just no longer the ``/chat`` call site) with a
real pipeline:

    retrieved chunks
      -> pre-filter (need >=2 distinct documents; existing optimization)
      -> claim extraction (1 batched LLM call; degrades to whole-chunk claims
         on failure)
      -> candidate filtering (deterministic entity/number/date signals,
         cross-document only, capped to settings.conflict_max_candidate_pairs)
      -> deterministic classification first (obvious numeric/date agreement
         or disagreement, no LLM call) -> LLM classification for the rest
         (1 batched call)
      -> aggregation into StructuredConflict rows + best-effort persistence

See ``pipeline.detect_conflicts_structured`` for the entry point.
"""

from .pipeline import detect_conflicts_structured
from .types import Claim, ConflictCandidate, Relationship, StructuredConflict

__all__ = [
    "Claim",
    "ConflictCandidate",
    "Relationship",
    "StructuredConflict",
    "detect_conflicts_structured",
]
