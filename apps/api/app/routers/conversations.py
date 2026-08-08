"""Conversation history — tenant + user scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_principal
from app.models import Conversation, Message
from app.rbac import Principal
from app.schemas import ConversationDetail, ConversationOut, MessageOut

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(
                Conversation.workspace_id == principal.workspace_id,
                Conversation.user_id == principal.user_id,
            )
            .order_by(Conversation.created_at.desc())
        )
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ConversationDetail:
    convo = db.get(Conversation, conversation_id)
    # 404 (not 403) for another tenant's/user's conversation.
    if (
        convo is None
        or convo.workspace_id != principal.workspace_id
        or convo.user_id != principal.user_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    # Both messages of a turn share a transaction timestamp, so break ties with
    # the user message before the assistant message.
    role_order = case((Message.role == "user", 0), else_=1)
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == convo.id)
            .order_by(Message.created_at, role_order)
        )
    )
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )
