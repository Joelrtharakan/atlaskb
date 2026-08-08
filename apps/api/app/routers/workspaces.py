"""Workspace management: create, members, role changes, and invites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.logging_config import get_logger
from app.models import (
    ROLE_ADMIN,
    Invite,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.rbac import get_membership, role_at_least
from app.schemas import (
    InviteOut,
    InviteRequest,
    MemberOut,
    RoleUpdate,
    WorkspaceCreate,
    WorkspaceOut,
)
from app.security import generate_invite_token

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
log = get_logger(__name__)


def _require_member(db: Session, workspace_id: str, user_id: str) -> WorkspaceMembership:
    membership = get_membership(db, workspace_id, user_id)
    if membership is None:
        # Don't reveal whether the workspace exists to non-members.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return membership


def _require_admin(db: Session, workspace_id: str, user_id: str) -> WorkspaceMembership:
    membership = _require_member(db, workspace_id, user_id)
    if not role_at_least(membership.role, ROLE_ADMIN):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only workspace admins can perform this action."
        )
    return membership


def _admin_count(db: Session, workspace_id: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == ROLE_ADMIN,
        )
    )


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkspaceOut:
    ws = Workspace(name=body.name)
    db.add(ws)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=ws.id, user_id=user.id, role=ROLE_ADMIN))
    audit.record(db, workspace_id=ws.id, user_id=user.id, action="workspace.create")
    db.commit()
    db.refresh(ws)
    log.info("workspace.create", workspace_id=ws.id, user_id=user.id)
    return WorkspaceOut(id=ws.id, name=ws.name, role=ROLE_ADMIN, created_at=ws.created_at)


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkspaceOut]:
    rows = db.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(Workspace.created_at)
    ).all()
    return [
        WorkspaceOut(id=w.id, name=w.name, role=role, created_at=w.created_at)
        for w, role in rows
    ]


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemberOut]:
    _require_member(db, workspace_id, user.id)
    rows = db.execute(
        select(WorkspaceMembership, User.email)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.joined_at)
    ).all()
    return [
        MemberOut(user_id=m.user_id, email=email, role=m.role, joined_at=m.joined_at)
        for m, email in rows
    ]


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
def change_role(
    workspace_id: str,
    user_id: str,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberOut:
    _require_admin(db, workspace_id, user.id)
    membership = get_membership(db, workspace_id, user_id)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user is not a member.")

    # Don't let the workspace lose its last admin.
    if membership.role == ROLE_ADMIN and body.role != ROLE_ADMIN and _admin_count(db, workspace_id) <= 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This is the workspace's only admin. Promote another member first.",
        )

    membership.role = body.role
    audit.record(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        action="member.role_change",
        target=user_id,
        meta={"role": body.role},
    )
    db.commit()
    db.refresh(membership)
    email = db.scalar(select(User.email).where(User.id == user_id))
    return MemberOut(user_id=user_id, email=email or "", role=membership.role, joined_at=membership.joined_at)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    _require_admin(db, workspace_id, user.id)
    membership = get_membership(db, workspace_id, user_id)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user is not a member.")
    if membership.role == ROLE_ADMIN and _admin_count(db, workspace_id) <= 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This is the workspace's only admin. Promote another member before removing them.",
        )
    db.delete(membership)
    audit.record(
        db, workspace_id=workspace_id, user_id=user.id, action="member.remove", target=user_id
    )
    db.commit()


@router.post("/{workspace_id}/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    workspace_id: str,
    body: InviteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InviteOut:
    _require_admin(db, workspace_id, user.id)

    email = body.email.lower()
    # If they're already a member, there's nothing to invite.
    already = db.scalar(
        select(WorkspaceMembership.id)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id, func.lower(User.email) == email)
    )
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "That user is already a member.")

    token = generate_invite_token()
    invite = Invite(
        workspace_id=workspace_id,
        email=email,
        role=body.role,
        token=token,
        invited_by=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.invite_ttl_days),
    )
    db.add(invite)
    audit.record(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        action="invite.create",
        target=email,
        meta={"role": body.role},
    )
    db.commit()
    db.refresh(invite)
    log.info("workspace.invite", workspace_id=workspace_id, email=email, role=body.role)

    # Point at the web app's accept page (a GET route that then POSTs to the API),
    # not the API's POST endpoint — otherwise opening the link in a browser 405s.
    base = settings.web_base_url.rstrip("/")
    return InviteOut(
        id=invite.id,
        workspace_id=invite.workspace_id,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        invite_url=f"{base}/invites/{invite.token}",
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
    )
