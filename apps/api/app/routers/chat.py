"""Q&A endpoint: cache → LangGraph agent (RBAC-scoped retrieval) → grounded answer.

Accepts JWT or API-key auth, is tenant/ACL-scoped, rate-limited, and persists the
turn to a tenant-scoped conversation.
"""

from __future__ import annotations

import hashlib

import openai
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm
from app.agent import run_agent
from app.cache import cache_get, cache_key, cache_set
from app.config import settings
from app.db import get_db
from app.deps import get_principal
from app.embeddings import embed_query
from app.llm import CANNOT_ANSWER
from app.logging_config import get_logger
from app.models import Conversation, Message
from app.ratelimit import check_rate_limit
from app.rbac import Principal
from app.retrieval import hybrid_search
from app.schemas import ChatRequest, ChatResponse, Citation, ScoredChunk, TokenUsageOut

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger(__name__)


def _resolve_conversation(
    db: Session, principal: Principal, conversation_id: str | None, question: str
) -> Conversation:
    if conversation_id:
        convo = db.get(Conversation, conversation_id)
        # 404 for another tenant's/user's conversation — never confirm it exists.
        if (
            convo is None
            or convo.workspace_id != principal.workspace_id
            or convo.user_id != principal.user_id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        return convo

    convo = Conversation(
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        title=question[:300],
    )
    db.add(convo)
    db.flush()
    return convo


def _load_history(db: Session, conversation_id: str) -> list[dict]:
    """Prior turns of a conversation, oldest first, as ``{role, content}`` dicts."""
    rows = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        .scalars()
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in rows]


def _history_sig(history: list[dict]) -> str:
    """Short digest of the conversation so far — folded into the cache key so a
    follow-up like "has that changed?" cannot collide across conversations."""
    if not history:
        return "0"
    joined = "\x1f".join(f"{m['role']}:{m['content']}" for m in history)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ChatResponse:
    check_rate_limit(principal)
    convo = _resolve_conversation(db, principal, body.conversation_id, body.question)
    # Prior turns (before this question) drive follow-up reference resolution.
    history = _load_history(db, convo.id)
    db.add(
        Message(
            conversation_id=convo.id,
            workspace_id=principal.workspace_id,
            role="user",
            content=body.question,
        )
    )

    key = cache_key(
        namespace="chat",
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        # Conversation history is part of the key: the same follow-up text means
        # different things in different threads, so answers must not be shared.
        model=f"{settings.llm_model}:k{body.top_k}:h{_history_sig(history)}",
        query=body.question,
    )
    cached = cache_get(key)
    if cached is not None:
        db.add(
            Message(
                conversation_id=convo.id,
                workspace_id=principal.workspace_id,
                role="assistant",
                content=cached["answer"],
            )
        )
        db.commit()
        log.info("chat.answer", user_id=principal.user_id, cached=True)
        return ChatResponse(
            answerable=cached["answerable"],
            answer=cached["answer"],
            citations=[Citation(**c) for c in cached["citations"]],
            retrieved=[ScoredChunk(**c) for c in cached["retrieved"]],
            cached=True,
            conversation_id=convo.id,
            iterations=cached.get("iterations", 0),
            queries=cached.get("queries", []),
            # A cache hit spends no tokens.
            usage=TokenUsageOut(),
        )

    def retrieve(query: str):
        embedding = embed_query(query)
        return hybrid_search(db, query, embedding, principal, top_k=body.top_k)

    # On a follow-up turn, bind the conversation history into the condense
    # (query-rewrite) and generation steps; first turns keep single-turn behavior.
    condense_fn = (lambda q: llm.condense_query(history, q)) if history else None
    generate_fn = (
        (lambda q, ch: llm.generate_answer(q, ch, history=history)) if history else None
    )

    try:
        result = run_agent(
            body.question, retrieve, condense_fn=condense_fn, generate_fn=generate_fn
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except openai.APIConnectionError as exc:
        # Can't reach the LLM daemon (e.g. Ollama not running). Give an actionable
        # message without leaking the client stack trace to the API caller.
        log.warning("chat.llm_unreachable", error=str(exc))
        if settings.llm_provider == "ollama":
            detail = (
                f"Ollama is unavailable at {settings.ollama_base_url}. "
                f"Start Ollama and ensure {settings.ollama_model} is installed."
            )
        else:
            detail = "LLM provider is unreachable."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)
    except openai.APIError as exc:
        log.warning("chat.llm_error", error=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM provider error: {exc}")

    grounded = result.answer
    retrieved = [
        ScoredChunk(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            text=h.text,
            page_num=h.page_num,
            section=h.section,
            score=h.score,
            dense_score=h.dense_score,
            sparse_score=h.sparse_score,
        )
        for h in result.chunks
    ]
    answer = grounded.answer if grounded.answerable else CANNOT_ANSWER
    citations = (
        [Citation(**c) for c in grounded.citations] if grounded.answerable else []
    )

    db.add(
        Message(
            conversation_id=convo.id,
            workspace_id=principal.workspace_id,
            role="assistant",
            content=answer,
        )
    )
    db.commit()

    usage = TokenUsageOut(
        prompt=result.usage.prompt,
        completion=result.usage.completion,
        total=result.usage.total,
    )
    payload = ChatResponse(
        answerable=grounded.answerable,
        answer=answer,
        citations=citations,
        retrieved=retrieved,
        cached=False,
        conversation_id=convo.id,
        iterations=result.iterations,
        queries=result.queries,
        usage=usage,
    )
    # Write-through (without the per-request conversation_id / cached flag).
    cache_set(
        key,
        {
            "answerable": payload.answerable,
            "answer": payload.answer,
            "citations": [c.model_dump() for c in payload.citations],
            "retrieved": [r.model_dump() for r in payload.retrieved],
            "iterations": payload.iterations,
            "queries": payload.queries,
        },
    )
    log.info(
        "chat.answer",
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        answerable=payload.answerable,
        iterations=payload.iterations,
        tokens=usage.total,
        cached=False,
    )
    return payload
