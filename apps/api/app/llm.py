"""Grounded answer generation via an OpenAI-compatible LLM API.

The provider is selected by ``settings.llm_provider`` ("ollama" by default, or
"openrouter"); both speak the same chat-completions API so one client serves
both. The model is instructed to answer *only* from the retrieved chunks and to
return structured JSON mapping each claim to the chunk IDs that support it. If it
cannot ground an answer, it must say so — we never fall back to the model's
general knowledge. The endpoint short-circuits to the same "cannot answer"
response when retrieval returns nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.config import settings
from app.retrieval import RetrievedChunk

CANNOT_ANSWER = "I cannot answer this question from the available documents."


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting for a single request or an accumulated run."""

    prompt: int = 0
    completion: int = 0
    total: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
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
- Every factual claim about the documents must be supported by one or more chunks, cited by their exact CHUNK_ID.
- If the context does not contain enough information to answer, set "answerable" to false and do not fabricate an answer.
- Use the prior conversation turns (if any) to resolve pronouns and references such as
  "it", "that", "this policy", or "the previous answer". The user's latest question may
  depend on earlier turns.
- If the question assumes a fact that the context does not support (a false premise),
  do not invent an answer: set "answerable" to true only if you can correct it from the
  context, and state plainly that the documents do not support the premise.
- You may also answer questions about the conversation ITSELF — for example, summarizing
  what the user has asked so far, or quoting your own earlier answer. Such conversational
  answers draw on the conversation history rather than the documents, and for them
  "citations" may be an empty list.

Respond with a single JSON object of exactly this shape:
{
  "answerable": boolean,
  "answer": string,
  "citations": [ { "claim": string, "chunk_ids": [string, ...] } ]
}
When "answerable" is false, "answer" should briefly state that the documents do not contain the answer, and "citations" should be an empty list.
"""


_CONDENSE_PROMPT = """\
You rewrite a user's latest message into a single standalone search query for a
keyword + semantic document search. Use the conversation so far to resolve
pronouns and references (e.g. "it", "that", "the policy", "its safety features")
into explicit terms.

Output ONLY the rewritten query text — no quotes, no explanation.
- If the latest message is already self-contained, return it unchanged.
- If it is about the conversation itself (e.g. "what have I asked?", "quote your
  last answer"), return it unchanged.
"""


def condense_query(history: list[dict], question: str) -> tuple[str, TokenUsage]:
    """Rewrite a follow-up into a standalone retrieval query using conversation history.

    Returns ``(query, usage)``. With no history this is a no-op (no LLM call). On any
    error it degrades to the original question so retrieval always has something to run.
    """
    if not history:
        return question, TokenUsage()
    try:
        client = _client()
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-8:])
        completion = client.chat.completions.create(
            model=settings.llm_model,
            temperature=0,
            messages=[
                *_no_think_prefix(),
                {"role": "system", "content": _CONDENSE_PROMPT},
                {
                    "role": "user",
                    "content": f"Conversation so far:\n{convo}\n\nLatest user message: {question}\n\nStandalone search query:",
                },
            ],
        )
        usage = _usage_from(completion)
        text = (completion.choices[0].message.content or "").strip().strip('"').strip()
        return (text or question), usage
    except Exception:  # noqa: BLE001 - degrade to the raw question on any failure
        return question, TokenUsage()


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
            model=settings.llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                *_no_think_prefix(),
                {"role": "system", "content": _ASSESS_PROMPT},
                {
                    "role": "user",
                    "content": f"Context chunks:\n\n{build_context(chunks)}\n\nQuestion: {question}",
                },
            ],
        )
        usage = _usage_from(completion)
        data = _parse_json_object(completion.choices[0].message.content or "{}")
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
    """OpenAI-compatible client for the configured provider.

    Ollama needs no key and exposes its OpenAI-compatible API under ``/v1``.
    OpenRouter requires a key. The returned client is used identically by every
    call site.
    """
    from openai import OpenAI

    if settings.llm_provider == "ollama":
        base = settings.ollama_base_url.rstrip("/")
        # Ollama ignores the key but the OpenAI client requires a non-empty one.
        return OpenAI(api_key="ollama", base_url=f"{base}/v1")

    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set; LLM_PROVIDER=openrouter requires an OpenRouter key."
        )
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def _no_think_prefix() -> list[dict]:
    """Leading system message that disables Qwen3's chain-of-thought on Ollama.

    Qwen3 defaults to emitting a long ``<think>`` reasoning trace, which on an 8B
    local model routinely exceeds client timeouts (observed >180s for a single
    query rewrite). ``/no_think`` is Qwen3's documented soft switch; placed as the
    first message it turns thinking off for the request. Grounding is unaffected —
    the answer is still constrained to the retrieved context. Scoped to the Ollama
    provider so hosted models are untouched.
    """
    return [{"role": "system", "content": "/no_think"}] if settings.llm_provider == "ollama" else []


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _parse_json_object(raw: str) -> dict:
    """Parse a JSON object from a model response, tolerating reasoning models.

    Qwen3 and similar "thinking" models may prepend a ``<think>...</think>`` block
    or wrap the JSON in prose/code fences even when asked for JSON. We strip the
    reasoning block, then fall back to extracting the outermost ``{...}`` span.
    Raises ``json.JSONDecodeError`` if no JSON object can be recovered, so callers
    keep their existing degrade-to-"cannot answer" behavior.
    """
    text = _THINK_RE.sub("", raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def ollama_health() -> dict:
    """Best-effort probe of the Ollama daemon for the health endpoint.

    Never raises. Returns a small status dict describing reachability and whether
    the configured model is installed. Only meaningful when provider == ollama.
    """
    status = {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "reachable": False,
        "model_available": False,
    }
    if settings.llm_provider != "ollama":
        return status
    try:
        import httpx

        base = settings.ollama_base_url.rstrip("/")
        resp = httpx.get(f"{base}/api/tags", timeout=3.0)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        status["reachable"] = True
        # Ollama reports tags like "qwen3:8b"; also match a bare model name.
        status["model_available"] = any(
            n == settings.ollama_model or n.split(":")[0] == settings.ollama_model.split(":")[0]
            for n in names
        )
    except Exception:  # noqa: BLE001 - health probe must never raise
        pass
    return status


def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[dict] | None = None,
) -> GroundedAnswer:
    """Call the LLM and return a validated grounded answer.

    Citations are filtered to chunk IDs that were actually retrieved, so the
    model cannot cite something outside the provided context. When ``history`` is
    provided (a follow-up turn), prior messages are included so the model can
    resolve references and answer questions about the conversation itself.
    """
    # With neither documents nor history there is nothing to ground an answer on.
    if not chunks and not history:
        return GroundedAnswer(False, CANNOT_ANSWER, [])

    client = _client()
    context = build_context(chunks)
    valid_ids = {c.chunk_id for c in chunks}

    messages: list[dict] = [*_no_think_prefix(), {"role": "system", "content": _SYSTEM_PROMPT}]
    for m in (history or [])[-8:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append(
        {"role": "user", "content": f"Context chunks:\n\n{context}\n\nQuestion: {question}"}
    )

    completion = client.chat.completions.create(
        model=settings.llm_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=messages,
    )
    usage = _usage_from(completion)
    raw = completion.choices[0].message.content or "{}"
    try:
        data = _parse_json_object(raw)
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

    # A document-grounded answer must actually cite retrieved chunks; otherwise
    # treat it as ungrounded rather than trusting an uncited claim. Follow-up
    # turns are exempt: a conversational/meta answer (e.g. summarizing what the
    # user asked) legitimately draws on the conversation history, not documents.
    if not citations and not history:
        return GroundedAnswer(False, CANNOT_ANSWER, [], usage)

    return GroundedAnswer(True, data.get("answer") or "", citations, usage)
