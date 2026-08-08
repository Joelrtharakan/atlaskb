"""Tiny audit-log helper. Records workspace-scoped admin/editor actions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    workspace_id: str,
    user_id: str | None,
    action: str,
    target: str | None = None,
    meta: dict | None = None,
) -> None:
    """Append an audit entry. The caller owns the surrounding transaction."""
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            target=target,
            meta=meta,
        )
    )
