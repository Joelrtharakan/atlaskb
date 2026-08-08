"""Admin surfaces: analytics (real tenant counts) and eval results."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import require_role
from app.models import (
    ROLE_ADMIN,
    ApiKey,
    Chunk,
    Conversation,
    Document,
    Message,
    WorkspaceMembership,
)
from app.rbac import Principal
from app.redis_client import get_redis
from app.schemas import AnalyticsResponse, DailyCount

router = APIRouter(prefix="/admin", tags=["admin"])


def _count_cache_entries() -> int:
    """Count semantic-cache entries currently in Redis (best-effort)."""
    try:
        redis = get_redis()
        return sum(1 for _ in redis.scan_iter(match=f"{settings.cache_prefix}:*", count=500))
    except Exception:  # noqa: BLE001 - analytics must not fail on a cache outage
        return 0


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> AnalyticsResponse:
    tenant = principal.workspace_id

    status_rows = db.execute(
        select(Document.status, func.count())
        .where(Document.workspace_id == tenant)
        .group_by(Document.status)
    ).all()
    by_status = {s: c for s, c in status_rows}
    documents_total = sum(by_status.values())

    chunks_total = db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.workspace_id == tenant)
    )
    conversations_total = db.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.workspace_id == tenant)
    )
    messages_total = db.scalar(
        select(func.count()).select_from(Message).where(Message.workspace_id == tenant)
    )
    members_total = db.scalar(
        select(func.count()).select_from(WorkspaceMembership).where(WorkspaceMembership.workspace_id == tenant)
    )
    active_api_keys = db.scalar(
        select(func.count())
        .select_from(ApiKey)
        .where(ApiKey.workspace_id == tenant, ApiKey.revoked_at.is_(None))
    )

    # Questions/day for the last 7 days (a "user" message == one asked question).
    since = datetime.now(UTC) - timedelta(days=7)
    day = func.date_trunc("day", Message.created_at)
    rows = db.execute(
        select(day.label("d"), func.count())
        .where(
            Message.workspace_id == tenant,
            Message.role == "user",
            Message.created_at >= since,
        )
        .group_by("d")
        .order_by("d")
    ).all()
    daily = [DailyCount(day=d.date().isoformat(), count=c) for d, c in rows]

    return AnalyticsResponse(
        workspace_id=tenant,
        documents_total=documents_total,
        documents_by_status=by_status,
        chunks_total=chunks_total or 0,
        conversations_total=conversations_total or 0,
        messages_total=messages_total or 0,
        members_total=members_total or 0,
        active_api_keys=active_api_keys or 0,
        cache_entries=_count_cache_entries(),
        questions_last_7_days=daily,
    )


@router.get("/evals")
def evals(
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> dict[str, Any]:
    """Return the most recent eval run, or a not-available marker.

    Eval results are a repo/CI artifact written by ``eval/run_eval.py``; this
    endpoint surfaces whatever the runner last produced.
    """
    path = Path(settings.eval_results_path)
    if not path.exists():
        return {"available": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Eval results exist but could not be read: {exc}",
        )
    data["available"] = True
    return data
