"""Workspace (tenant) management: create, members, invite, role assignment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_principal
from app.logging_config import get_logger
from app.models import ROLE_ADMIN, Tenant, TenantMembership, User
from app.rbac import Principal, get_membership, role_at_least
from app.schemas import (
    InviteRequest,
    MemberOut,
    RoleUpdate,
    WorkspaceCreate,
    WorkspaceOut,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
log = get_logger(__name__)


def _require_admin(db: Session, tenant_id: str, user_id: str) -> TenantMembership:
    membership = get_membership(db, tenant_id, user_id)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    if not role_at_least(membership.role, ROLE_ADMIN):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only workspace admins can perform this action."
        )
    return membership


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkspaceOut:
    tenant = Tenant(name=body.name)
    db.add(tenant)
    db.flush()
    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=ROLE_ADMIN))
    db.commit()
    db.refresh(tenant)
    log.info("workspace.create", tenant_id=tenant.id, user_id=user.id)
    return WorkspaceOut(id=tenant.id, name=tenant.name, role=ROLE_ADMIN, created_at=tenant.created_at)


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkspaceOut]:
    rows = db.execute(
        select(Tenant, TenantMembership.role)
        .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
        .where(TenantMembership.user_id == user.id)
        .order_by(Tenant.created_at)
    ).all()
    return [
        WorkspaceOut(id=t.id, name=t.name, role=role, created_at=t.created_at)
        for t, role in rows
    ]


@router.get("/{workspace_id}/members", response_model=list[MemberOut])
def list_members(
    workspace_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[MemberOut]:
    # Must be a member of the workspace being inspected.
    if principal.tenant_id != workspace_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Select this workspace with the X-Tenant-Id header to view its members.",
        )
    rows = db.execute(
        select(TenantMembership, User.email)
        .join(User, User.id == TenantMembership.user_id)
        .where(TenantMembership.tenant_id == workspace_id)
        .order_by(TenantMembership.created_at)
    ).all()
    return [
        MemberOut(
            user_id=m.user_id, email=email, role=m.role, created_at=m.created_at
        )
        for m, email in rows
    ]


@router.post("/{workspace_id}/invite", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def invite_member(
    workspace_id: str,
    body: InviteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberOut:
    _require_admin(db, workspace_id, user.id)

    invitee = db.scalar(select(User).where(User.email == body.email))
    if invitee is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No AtlasKB user with that email. Ask them to sign up first, then invite them.",
        )

    existing = get_membership(db, workspace_id, invitee.id)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That user is already a member of this workspace."
        )

    membership = TenantMembership(
        tenant_id=workspace_id, user_id=invitee.id, role=body.role
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    log.info("workspace.invite", tenant_id=workspace_id, user_id=invitee.id, role=body.role)
    return MemberOut(
        user_id=invitee.id, email=invitee.email, role=membership.role, created_at=membership.created_at
    )


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberOut)
def assign_role(
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

    membership.role = body.role
    db.commit()
    db.refresh(membership)
    member_email = db.scalar(select(User.email).where(User.id == user_id))
    log.info("workspace.assign_role", tenant_id=workspace_id, user_id=user_id, role=body.role)
    return MemberOut(
        user_id=user_id, email=member_email or "", role=membership.role, created_at=membership.created_at
    )
