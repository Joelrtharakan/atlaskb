"""Q&A endpoint: cache → LangGraph agent (RBAC-scoped retrieval) → grounded answer.

Accepts JWT or API-key auth, is tenant/ACL-scoped, rate-limited, and persists the
turn to a tenant-scoped conversation.
"""

from __future__ import annotations

import openai
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
from app.schemas import ChatRequest, ChatResponse, Citation, ScoredChunk

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
            or convo.tenant_id != principal.tenant_id
            or convo.user_id != principal.user_id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        return convo

    convo = Conversation(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        title=question[:300],
    )
    db.add(convo)
    db.flush()
    return convo


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ChatResponse:
    check_rate_limit(principal)
    convo = _resolve_conversation(db, principal, body.conversation_id, body.question)
    db.add(
        Message(
            conversation_id=convo.id,
            tenant_id=principal.tenant_id,
            role="user",
            content=body.question,
        )
    )

    key = cache_key(
        namespace="chat",
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        model=f"{settings.openrouter_model}:k{body.top_k}",
        query=body.question,
    )
    cached = cache_get(key)
    if cached is not None:
        db.add(
            Message(
                conversation_id=convo.id,
                tenant_id=principal.tenant_id,
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
        )

    def retrieve(query: str):
        embedding = embed_query(query)
        return hybrid_search(db, query, embedding, principal, top_k=body.top_k)

    try:
        result = run_agent(body.question, retrieve)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
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
            tenant_id=principal.tenant_id,
            role="assistant",
            content=answer,
        )
    )
    db.commit()

    payload = ChatResponse(
        answerable=grounded.answerable,
        answer=answer,
        citations=citations,
        retrieved=retrieved,
        cached=False,
        conversation_id=convo.id,
        iterations=result.iterations,
        queries=result.queries,
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
        tenant_id=principal.tenant_id,
        answerable=payload.answerable,
        iterations=payload.iterations,
        cached=False,
    )
    return payload
