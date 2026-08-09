"""Dashboard summary endpoints.

Feeds the Relief Map: every document the caller may see, with its "mass" (chunk
count → peak height) and staleness (→ valley). ACL-scoped exactly like the
documents list, so a restricted document never surfaces on the map.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_principal
from app.models import Chunk, Document
from app.rbac import Principal, document_visible_clause
from app.schemas import ReliefCell, ReliefSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/relief", response_model=ReliefSummary)
def relief(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ReliefSummary:
    # chunk_count per document in one grouped query (avoids N+1).
    counts = dict(
        db.execute(
            select(Chunk.document_id, func.count())
            .where(Chunk.workspace_id == principal.workspace_id)
            .group_by(Chunk.document_id)
        ).all()
    )
    docs = db.scalars(
        select(Document)
        .where(
            Document.workspace_id == principal.workspace_id,
            document_visible_clause(principal),
        )
        .order_by(Document.created_at.desc())
    ).all()
    cells = [
        ReliefCell(
            id=d.id,
            filename=d.filename,
            status=d.status,
            mass=int(counts.get(d.id, 0)),
            staleness=d.staleness,
        )
        for d in docs
    ]
    return ReliefSummary(cells=cells)
