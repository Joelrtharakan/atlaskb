"""Claim extraction: turns retrieved chunks into atomic factual claims via one
batched LLM call, so later pipeline stages compare specific assertions rather
than whole chunks (a chunk can carry several claims, only one of which
actually conflicts with another source). Degrades to treating each whole
chunk's text as a single claim if the LLM call fails or returns nothing
usable — conflict detection still runs, just at chunk granularity instead of
claim granularity, rather than losing the signal entirely.
"""

from __future__ import annotations

from app import llm as llm_module
from app.config import settings
from app.retrieval import RetrievedChunk

from .signals import extract_dates, extract_entities, extract_numbers
from .types import Claim

_CLAIM_EXTRACTION_PROMPT = """\
For each numbered chunk below, extract the 1-3 atomic factual claims it makes
— each claim a single self-contained sentence, preserving exact numbers,
dates, and names from the source verbatim. Skip chunks that make no factual
claims (pure narrative with nothing verifiable).

Respond with a single JSON object of exactly this shape:
{
  "claims": [ { "chunk_index": integer, "text": string } ]
}
"chunk_index" is the 0-based position of the source chunk in the input list.
"""


def extract_claims(
    chunks: list[RetrievedChunk],
) -> tuple[list[Claim], llm_module.TokenUsage]:
    if not chunks:
        return [], llm_module.TokenUsage()

    listing = "\n\n".join(f"Chunk {i}:\n{c.text}" for i, c in enumerate(chunks))
    try:
        client = llm_module._client()
        completion = llm_module.create_completion(
            client,
            model=settings.conflict_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                *llm_module._no_think_prefix(),
                {"role": "system", "content": _CLAIM_EXTRACTION_PROMPT},
                {"role": "user", "content": listing},
            ],
        )
        usage = llm_module._usage_from(completion)
        data = llm_module._parse_json_object(completion.choices[0].message.content or "{}")
        raw_claims = data.get("claims", []) or []
    except Exception:  # noqa: BLE001 - claim extraction is best-effort, never blocks the answer
        return _fallback_whole_chunk_claims(chunks), llm_module.TokenUsage()

    claims: list[Claim] = []
    for rc in raw_claims:
        idx = rc.get("chunk_index")
        text = (rc.get("text") or "").strip()
        if not isinstance(idx, int) or not (0 <= idx < len(chunks)) or not text:
            continue
        source = chunks[idx]
        claims.append(
            Claim(
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                version_id=source.version_id,
                text=text,
                numbers=extract_numbers(text),
                dates=extract_dates(text),
                entities=extract_entities(text),
            )
        )
    if not claims:
        return _fallback_whole_chunk_claims(chunks), usage
    return claims, usage


def _fallback_whole_chunk_claims(chunks: list[RetrievedChunk]) -> list[Claim]:
    return [
        Claim(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            version_id=c.version_id,
            text=c.text,
            numbers=extract_numbers(c.text),
            dates=extract_dates(c.text),
            entities=extract_entities(c.text),
        )
        for c in chunks
    ]
