"""Role-based access control primitives.

A :class:`Principal` is the resolved identity for a request: which user, acting in
which tenant, with which role, authenticated how. Every tenant-scoped query is
built from a Principal so isolation is enforced consistently in one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models import (
    ROLE_ADMIN,
    ROLES,
    Document,
    DocumentACL,
    TenantMembership,
)

# Privilege ordering for "at least this role" checks.
_RANK = {role: i for i, role in enumerate(ROLES)}


def role_at_least(role: str, minimum: str) -> bool:
    return _RANK.get(role, -1) >= _RANK.get(minimum, 999)


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str
    auth: str  # "jwt" | "api_key"

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def get_membership(db: Session, tenant_id: str, user_id: str) -> TenantMembership | None:
    return db.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )


def document_visible_clause(principal: Principal):
    """A SQL predicate (on the ``documents`` table) that is true only for
    documents the principal may read within their tenant.

    Rules: the document must belong to the principal's tenant, and — unless the
    principal is a tenant admin or the document's owner — the document must
    either have no ACL entries (open to all members) or an ACL entry naming the
    principal.
    """
    tenant_match = Document.tenant_id == principal.tenant_id
    if principal.is_admin:
        return tenant_match

    has_acl = exists(select(DocumentACL.id).where(DocumentACL.document_id == Document.id))
    named_in_acl = exists(
        select(DocumentACL.id).where(
            DocumentACL.document_id == Document.id,
            DocumentACL.user_id == principal.user_id,
        )
    )
    return and_(
        tenant_match,
        or_(Document.owner_id == principal.user_id, ~has_acl, named_in_acl),
    )
