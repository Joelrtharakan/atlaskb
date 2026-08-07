"""Grounded answer generation via OpenRouter (OpenAI-compatible API).

The model is instructed to answer *only* from the retrieved chunks and to return
structured JSON mapping each claim to the chunk IDs that support it. If it cannot
ground an answer, it must say so — we never fall back to the model's general
knowledge. The endpoint short-circuits to the same "cannot answer" response when
retrieval returns nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import settings
from app.retrieval import RetrievedChunk

CANNOT_ANSWER = "I cannot answer this question from the available documents."


@dataclass(frozen=True)
class TokenUsage:
    """OpenRouter token accounting for a single request or an accumulated run."""

    prompt: int = 0
    completion: int = 0
    total: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.prompt + other.prompt,
            self.completion + other.completion,
            self.total + other.total,
        )


def _usage_from(completion) -> TokenUsage:
    u = getattr(completion, "usage", None)
    if u is None:
        return TokenUsage()
    return TokenUsage(
        prompt=getattr(u, "prompt_tokens", 0) or 0,
        completion=getattr(u, "completion_tokens", 0) or 0,
        total=getattr(u, "total_tokens", 0) or 0,
    )

_SYSTEM_PROMPT = """\
You are AtlasKB, a retrieval-grounded question answering assistant.

Rules:
- Answer ONLY using the provided context chunks. Never use outside/general knowledge.
- Every factual claim in your answer must be supported by one or more chunks, cited by their exact CHUNK_ID.
- If the context does not contain enough information to answer, set "answerable" to false and do not fabricate an answer.

Respond with a single JSON object of exactly this shape:
{
  "answerable": boolean,
  "answer": string,
  "citations": [ { "claim": string, "chunk_ids": [string, ...] } ]
}
When "answerable" is false, "answer" should briefly state that the documents do not contain the answer, and "citations" should be an empty list.
"""


def build_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for c in chunks:
        loc = []
        if c.page_num is not None:
            loc.append(f"page {c.page_num}")
        if c.section:
            loc.append(f"section: {c.section}")
        loc_str = f" ({', '.join(loc)})" if loc else ""
        parts.append(f"CHUNK_ID: {c.chunk_id}{loc_str}\n{c.text}")
    return "\n\n---\n\n".join(parts)


class GroundedAnswer:
    def __init__(
        self,
        answerable: bool,
        answer: str,
        citations: list[dict],
        usage: TokenUsage | None = None,
    ):
        self.answerable = answerable
        self.answer = answer
        self.citations = citations
        self.usage = usage or TokenUsage()


class Assessment:
    """The agent's judgement on whether retrieved context can answer the question."""

    def __init__(
        self,
        sufficient: bool,
        refined_query: str | None = None,
        usage: TokenUsage | None = None,
    ):
        self.sufficient = sufficient
        self.refined_query = refined_query
        self.usage = usage or TokenUsage()


_ASSESS_PROMPT = """\
You are the retrieval planner for AtlasKB. Given a user question and the context
chunks retrieved so far, decide whether they are sufficient to fully answer the
question using ONLY that context.

Respond with a single JSON object:
{
  "sufficient": boolean,
  "refined_query": string
}
Set "sufficient" to true if the chunks already contain enough to answer. If not,
set "sufficient" to false and put in "refined_query" a better search query (different
wording, more specific terms) likely to retrieve the missing information. When
"sufficient" is true, "refined_query" may be an empty string.
"""


def assess_context(question: str, chunks: list[RetrievedChunk]) -> Assessment:
    """Ask the LLM whether ``chunks`` suffice, and if not, how to re-query.

    Falls back to "sufficient" if there are chunks and the model errors — the
    generator will still refuse if they cannot actually ground an answer.
    """
    if not chunks:
        return Assessment(sufficient=False, refined_query=question)

    try:
        client = _client()
        completion = client.chat.completions.create(
            model=settings.openrouter_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _ASSESS_PROMPT},
                {
                    "role": "user",
                    "content": f"Context chunks:\n\n{build_context(chunks)}\n\nQuestion: {question}",
                },
            ],
        )
        usage = _usage_from(completion)
        data = json.loads(completion.choices[0].message.content or "{}")
    except (json.JSONDecodeError, Exception):  # noqa: BLE001 - degrade gracefully
        return Assessment(sufficient=True, refined_query=None)

    sufficient = bool(data.get("sufficient"))
    refined = (data.get("refined_query") or "").strip() or None
    return Assessment(
        sufficient=sufficient,
        refined_query=None if sufficient else refined,
        usage=usage,
    )


def _client():
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set; /chat requires an OpenRouter key."
        )
    from openai import OpenAI

    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def generate_answer(question: str, chunks: list[RetrievedChunk]) -> GroundedAnswer:
    """Call the LLM and return a validated grounded answer.

    Citations are filtered to chunk IDs that were actually retrieved, so the
    model cannot cite something outside the provided context.
    """
    if not chunks:
        return GroundedAnswer(False, CANNOT_ANSWER, [])

    client = _client()
    context = build_context(chunks)
    valid_ids = {c.chunk_id for c in chunks}

    completion = client.chat.completions.create(
        model=settings.openrouter_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Context chunks:\n\n{context}\n\nQuestion: {question}",
            },
        ],
    )
    usage = _usage_from(completion)
    raw = completion.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return GroundedAnswer(False, CANNOT_ANSWER, [], usage)

    answerable = bool(data.get("answerable"))
    if not answerable:
        return GroundedAnswer(False, data.get("answer") or CANNOT_ANSWER, [], usage)

    citations: list[dict] = []
    for cit in data.get("citations", []) or []:
        ids = [cid for cid in (cit.get("chunk_ids") or []) if cid in valid_ids]
        if ids:
            citations.append({"claim": cit.get("claim", ""), "chunk_ids": ids})

    # A grounded answer must actually cite retrieved chunks; otherwise treat it
    # as ungrounded rather than trusting an uncited claim.
    if not citations:
        return GroundedAnswer(False, CANNOT_ANSWER, [], usage)

    return GroundedAnswer(True, data.get("answer") or "", citations, usage)
