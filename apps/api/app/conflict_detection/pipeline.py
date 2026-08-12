"""Pipeline orchestration — see the package docstring for the full stage list.

The single entry point, ``detect_conflicts_structured``, is what
``app.routers.chat`` calls; ``app.llm.detect_conflicts`` (the old single-call
approach) is left in place, untouched, and still tested, but is no longer the
`/chat` call site.
"""

from __future__ import annotations

from app import llm as llm_module
from app.retrieval import RetrievedChunk

from .candidates import select_candidates
from .claims import extract_claims
from .deterministic import try_classify
from .llm_stage import classify_candidates
from .types import StructuredConflict


def detect_conflicts_structured(
    chunks: list[RetrievedChunk],
    *,
    candidate_min_similarity: float | None = None,
    candidate_max_pairs: int | None = None,
) -> tuple[list[StructuredConflict], llm_module.TokenUsage]:
    """Run the full pipeline over a set of retrieved chunks.

    Returns every classified candidate pair (all 5 relationship types), not
    only contradictions — callers that only want the "Sources disagree"
    signal should filter for ``relationship == Relationship.CONTRADICTS``
    themselves (see ``app.routers.chat``). Never raises: each stage degrades
    independently (claim extraction falls back to whole-chunk claims; LLM
    classification falls back to UNCERTAIN) so a partial failure never
    blocks the answer.

    ``candidate_min_similarity``/``candidate_max_pairs`` let a caller widen
    the candidate net for a single call (Trust Layer Phase 4's MAX_TRUST
    mode) without touching the process-wide defaults other requests use.
    """
    doc_ids = {c.document_id for c in chunks}
    if len(doc_ids) < 2:
        return [], llm_module.TokenUsage()

    claims, extract_usage = extract_claims(chunks)
    if len(claims) < 2:
        return [], extract_usage

    candidates = select_candidates(
        claims, min_similarity=candidate_min_similarity, max_pairs=candidate_max_pairs
    )
    if not candidates:
        return [], extract_usage

    resolved: list[StructuredConflict] = []
    remaining = []
    for candidate in candidates:
        deterministic_result = try_classify(candidate)
        if deterministic_result is not None:
            resolved.append(deterministic_result)
        else:
            remaining.append(candidate)

    llm_results, classify_usage = classify_candidates(remaining)
    resolved.extend(llm_results)

    return resolved, extract_usage + classify_usage
