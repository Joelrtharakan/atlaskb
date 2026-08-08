"""Invite acceptance: an authenticated user joins a workspace via an invite token."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import get_current_user
from app.logging_config import get_logger
from app.models import Invite, User, Workspace, WorkspaceMembership
from app.rbac import get_membership
from app.schemas import InviteAcceptOut, InvitePreview

router = APIRouter(prefix="/invites", tags=["invites"])
log = get_logger(__name__)


@router.get("/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)) -> InvitePreview:
    """Public preview of an invite so the accept page can show the (locked) email
    and workspace before the invitee has an account. Never requires auth."""
    invite = db.scalar(select(Invite).where(Invite.token == token))
    if invite is None:
        return InvitePreview(status="invalid")
    if invite.accepted_at is not None:
        state = "accepted"
    elif invite.expires_at <= datetime.now(UTC):
        state = "expired"
    else:
        state = "valid"
    workspace = db.get(Workspace, invite.workspace_id)
    return InvitePreview(
        status=state,
        email=invite.email,
        role=invite.role,
        workspace_id=invite.workspace_id,
        workspace_name=workspace.name if workspace else None,
    )


@router.post("/{token}/accept", response_model=InviteAcceptOut)
def accept_invite(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InviteAcceptOut:
    invite = db.scalar(select(Invite).where(Invite.token == token))
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    if invite.accepted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invite has already been used.")
    if invite.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "This invite has expired. Ask for a new one.")
    # An invite is bound to the email it was sent to.
    if invite.email.lower() != user.email.lower():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This invite was issued to a different email address.",
        )

    if get_membership(db, invite.workspace_id, user.id) is None:
        db.add(
            WorkspaceMembership(
                workspace_id=invite.workspace_id, user_id=user.id, role=invite.role
            )
        )
    invite.accepted_at = datetime.now(UTC)
    audit.record(
        db,
        workspace_id=invite.workspace_id,
        user_id=user.id,
        action="invite.accept",
        target=user.email,
        meta={"role": invite.role},
    )
    db.commit()
    log.info("invite.accept", workspace_id=invite.workspace_id, user_id=user.id)
    return InviteAcceptOut(workspace_id=invite.workspace_id, role=invite.role)
