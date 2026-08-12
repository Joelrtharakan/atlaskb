"""Best-effort persistence of every classified pipeline result (not only
CONTRADICTS) to the `conflicts` table — a full audit trail, available for
later cross-session/admin use even though `/chat`'s response only surfaces
CONTRADICTS pairs today.

Rows are always tagged with the caller's ``workspace_id`` and never written
across a tenant boundary, since the pipeline only ever runs over chunks
already RBAC/workspace-scoped by retrieval — there is nothing here that
*could* span two workspaces.

Uses the caller's request-scoped session and does not commit: the caller
(``app.routers.chat``) commits once, alongside the assistant message, so a
mid-request failure rolls both back together rather than leaving an orphaned
conflict record with no corresponding answer.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ConflictRecord

from .types import StructuredConflict


def persist(db: Session, *, workspace_id: str, conflicts: list[StructuredConflict]) -> None:
    for c in conflicts:
        db.add(
            ConflictRecord(
                workspace_id=workspace_id,
                document_id_a=c.document_id_a,
                document_version_a=c.document_version_a,
                chunk_id_a=c.chunk_id_a,
                claim_a=c.claim_a,
                document_id_b=c.document_id_b,
                document_version_b=c.document_version_b,
                chunk_id_b=c.chunk_id_b,
                claim_b=c.claim_b,
                relationship=c.relationship.value,
                confidence=c.confidence,
                explanation=c.explanation,
                method=c.method,
            )
        )
