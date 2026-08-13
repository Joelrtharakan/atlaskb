"""Conversation history — tenant + user scoped."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_principal
from app.models import Conversation, Message, MessageFeedback
from app.rbac import Principal
from app.schemas import ConversationDetail, ConversationOut, MessageOut

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[Conversation]:
    # "Most recent activity", not "most recently created" — a conversation
    # with a new message today must sort above one merely started yesterday.
    # last_activity falls back to created_at for a conversation with no
    # messages yet (the brief window right after creation).
    last_activity = (
        select(Message.conversation_id, func.max(Message.created_at).label("last_at"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    order_col = func.coalesce(last_activity.c.last_at, Conversation.created_at)
    return list(
        db.scalars(
            select(Conversation)
            .outerjoin(last_activity, last_activity.c.conversation_id == Conversation.id)
            .where(
                Conversation.workspace_id == principal.workspace_id,
                Conversation.user_id == principal.user_id,
            )
            .order_by(order_col.desc())
            .limit(limit)
            .offset(offset)
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
    feedback_by_message = dict(
        db.execute(
            select(MessageFeedback.message_id, MessageFeedback.rating).where(
                MessageFeedback.message_id.in_([m.id for m in messages]),
                MessageFeedback.user_id == principal.user_id,
            )
        ).all()
    )
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                feedback=feedback_by_message.get(m.id),
                response=m.response_json,
            )
            for m in messages
        ],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> None:
    convo = db.get(Conversation, conversation_id)
    # 404 (not 403) for another tenant's/user's conversation — same
    # never-confirm-existence discipline as GET.
    if (
        convo is None
        or convo.workspace_id != principal.workspace_id
        or convo.user_id != principal.user_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    db.delete(convo)  # cascades to messages/feedback — Conversation.messages is delete-orphan
    db.commit()
