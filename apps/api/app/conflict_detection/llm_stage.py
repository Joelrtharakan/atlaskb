"""LLM-backed relationship classification for candidate pairs the
deterministic stage couldn't confidently resolve.

One batched call classifies every surviving candidate at once (not one call
per pair), targeting ``settings.conflict_model`` — which can be a
smaller/faster model than generation, configured independently via
``CONFLICT_DETECTION_MODEL``. Reuses ``app.llm``'s client/JSON-parsing/
``/no_think`` helpers rather than reimplementing them.
"""

from __future__ import annotations

from app import llm as llm_module
from app.config import settings

from .types import ConflictCandidate, Relationship, StructuredConflict

_CLASSIFY_PROMPT = """\
You classify the relationship between pairs of claims drawn from different
documents. For EACH pair, decide exactly one relationship:

- SUPPORTS: both claims assert the same fact.
- CONTRADICTS: the claims assert incompatible facts about the same specific
  subject (a different number, date, or rule for the same thing).
- COMPLEMENTS: the claims are about the same general subject but describe
  different, non-conflicting aspects of it (e.g. one describes a process
  step, the other describes who is responsible for a different step).
- UNRELATED: the claims are not actually about the same subject, even if they
  use similar words.
- UNCERTAIN: you cannot confidently tell from the claim text alone.

Example — CONTRADICTS: "Employees receive 20 days of annual leave." vs
"Employees receive 25 days of annual leave." (same subject, incompatible
numbers.)

Example — COMPLEMENTS: "Employees submit leave requests through HR." vs
"Managers approve leave requests." (same general process, different steps —
not a disagreement.)

Only classify a pair as SUPPORTS or CONTRADICTS when both claims are about
the exact same specific subject. When genuinely unsure, use UNCERTAIN rather
than guessing — a false alarm is worse than a missed marginal case.

Respond with a single JSON object of exactly this shape:
{
  "results": [
    { "index": integer, "topic": string, "relationship": string, "confidence": number, "explanation": string }
  ]
}
"index" is the 0-based position of the pair in the input list. "topic" is a
short label for the shared subject. "confidence" is your own confidence in
this classification, from 0.0 to 1.0. "explanation" is one sentence.
"""


def classify_candidates(
    candidates: list[ConflictCandidate],
) -> tuple[list[StructuredConflict], llm_module.TokenUsage]:
    if not candidates:
        return [], llm_module.TokenUsage()

    pairs_text = "\n\n".join(
        f"Pair {i}:\n"
        f"Claim A (document {c.claim_a.document_id}): {c.claim_a.text}\n"
        f"Claim B (document {c.claim_b.document_id}): {c.claim_b.text}"
        for i, c in enumerate(candidates)
    )
    try:
        client = llm_module._client()
        completion = llm_module.create_completion(
            client,
            model=settings.conflict_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                *llm_module._no_think_prefix(),
                {"role": "system", "content": _CLASSIFY_PROMPT},
                {"role": "user", "content": pairs_text},
            ],
        )
        usage = llm_module._usage_from(completion)
        data = llm_module._parse_json_object(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001 - best-effort signal, must never block the answer
        # Degrade every surviving candidate to UNCERTAIN rather than silently
        # dropping them — an LLM outage should not look identical to "checked,
        # no conflicts found".
        return [
            _uncertain(c, "Classification unavailable (LLM error).") for c in candidates
        ], llm_module.TokenUsage()

    by_index: dict[int, dict] = {}
    for r in data.get("results", []) or []:
        idx = r.get("index")
        if isinstance(idx, int) and 0 <= idx < len(candidates):
            by_index[idx] = r

    results: list[StructuredConflict] = []
    for i, c in enumerate(candidates):
        r = by_index.get(i)
        if r is None:
            results.append(_uncertain(c, "Model did not return a classification for this pair."))
            continue
        rel_raw = str(r.get("relationship") or "UNCERTAIN").upper()
        try:
            rel = Relationship(rel_raw)
        except ValueError:
            rel = Relationship.UNCERTAIN
        conf_raw = r.get("confidence")
        confidence = max(0.0, min(1.0, float(conf_raw))) if isinstance(conf_raw, int | float) else 0.5
        results.append(
            StructuredConflict(
                topic=(str(r.get("topic") or "")[:200]) or "Cross-document claim comparison",
                document_id_a=c.claim_a.document_id,
                document_version_a=c.claim_a.version_id,
                chunk_id_a=c.claim_a.chunk_id,
                claim_a=c.claim_a.text,
                document_id_b=c.claim_b.document_id,
                document_version_b=c.claim_b.version_id,
                chunk_id_b=c.claim_b.chunk_id,
                claim_b=c.claim_b.text,
                relationship=rel,
                confidence=confidence,
                explanation=(str(r.get("explanation") or ""))[:500],
                method="llm",
            )
        )
    return results, usage


def _uncertain(candidate: ConflictCandidate, explanation: str) -> StructuredConflict:
    a, b = candidate.claim_a, candidate.claim_b
    return StructuredConflict(
        topic="Cross-document claim comparison",
        document_id_a=a.document_id,
        document_version_a=a.version_id,
        chunk_id_a=a.chunk_id,
        claim_a=a.text,
        document_id_b=b.document_id,
        document_version_b=b.version_id,
        chunk_id_b=b.chunk_id,
        claim_b=b.text,
        relationship=Relationship.UNCERTAIN,
        confidence=0.0,
        explanation=explanation,
        method="llm",
    )
