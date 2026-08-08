"""Role-based access control primitives.

A :class:`Principal` is the resolved identity for a request: which user, acting in
which workspace, with which role, authenticated how. Every workspace-scoped query
is built from a Principal so isolation is enforced consistently in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models import (
    GRANT_ROLE,
    GRANT_USER,
    ROLE_ADMIN,
    ROLES,
    Document,
    DocumentAccessGrant,
    WorkspaceMembership,
)

# Privilege ordering for "at least this role" checks.
_RANK = {role: i for i, role in enumerate(ROLES)}


def role_at_least(role: str, minimum: str) -> bool:
    return _RANK.get(role, -1) >= _RANK.get(minimum, 999)


@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    role: str
    auth: str  # "jwt" | "api_key"

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def get_membership(db: Session, workspace_id: str, user_id: str) -> WorkspaceMembership | None:
    return db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )


def document_visible_clause(principal: Principal):
    """A SQL predicate (on the ``documents`` table) true only for documents the
    principal may read within their workspace.

    Rules: the document must belong to the principal's workspace, and — unless the
    principal is a workspace admin or the document's owner — the document must
    either have no access grants (visible to all members) or a grant that matches
    the caller by named user or by role.
    """
    workspace_match = Document.workspace_id == principal.workspace_id
    if principal.is_admin:
        return workspace_match

    has_grant = exists(
        select(DocumentAccessGrant.id).where(DocumentAccessGrant.document_id == Document.id)
    )
    user_grant = exists(
        select(DocumentAccessGrant.id).where(
            DocumentAccessGrant.document_id == Document.id,
            DocumentAccessGrant.grant_type == GRANT_USER,
            DocumentAccessGrant.role_or_user_id == principal.user_id,
        )
    )
    role_grant = exists(
        select(DocumentAccessGrant.id).where(
            DocumentAccessGrant.document_id == Document.id,
            DocumentAccessGrant.grant_type == GRANT_ROLE,
            DocumentAccessGrant.role_or_user_id == principal.role,
        )
    )
    return and_(
        workspace_match,
        or_(Document.owner_id == principal.user_id, ~has_grant, user_grant, role_grant),
    )


def can_read_document(db: Session, principal: Principal, document: Document) -> bool:
    """Row-level equivalent of :func:`document_visible_clause` for a loaded
    document — used by direct-by-id lookups so isolation holds there too."""
    if document.workspace_id != principal.workspace_id:
        return False
    if principal.is_admin or document.owner_id == principal.user_id:
        return True
    grants = db.scalars(
        select(DocumentAccessGrant).where(DocumentAccessGrant.document_id == document.id)
    ).all()
    if not grants:
        return True
    for g in grants:
        if g.grant_type == GRANT_USER and g.role_or_user_id == principal.user_id:
            return True
        if g.grant_type == GRANT_ROLE and g.role_or_user_id == principal.role:
            return True
    return False
