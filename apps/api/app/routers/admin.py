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
from app.content_gaps import compute_gaps
from app.db import get_db
from app.deps import require_role
from app.models import (
    ROLE_ADMIN,
    ApiKey,
    AuditLog,
    Chunk,
    ContentGapResolution,
    Conversation,
    Document,
    Message,
    MessageFeedback,
    User,
    WorkspaceMembership,
)
from app.rbac import Principal
from app.redis_client import get_redis
from app.schemas import (
    AnalyticsResponse,
    AuditLogEntryOut,
    AuditLogResponse,
    ContentGap,
    ContentGapsResponse,
    DailyCount,
    EvalHeadline,
    FeedbackSummary,
    FeedbackSummaryResponse,
    QueryVolumePoint,
    QueryVolumeResponse,
)

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


def _eval_results_dir() -> Path:
    # eval_results_path points at .../eval/results/latest.json; the sibling
    # T9.1-T9.5 files (before_after, ablation, adversarial, prompt_injection,
    # latency_breakdown) live in the same directory.
    return Path(settings.eval_results_path).parent


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _build_headline(results_dir: Path) -> EvalHeadline:
    """Assemble the complete metrics picture purely from files on disk. Every
    field traces to a real eval/results/*.json produced by T9.1-T9.5 — nothing
    here is computed, estimated, or typed in by hand."""
    found: list[str] = []
    missing: list[str] = []

    def load(name: str) -> dict[str, Any] | None:
        data = _load_json(results_dir / name)
        (found if data is not None else missing).append(name)
        return data

    # "after" = the current full system, run under T9.1's before/after harness
    # over the same T7 dataset — has every metric latest.json has, plus
    # citation_coverage and a real permission-leakage check latest.json lacks.
    after = load("before_after_after.json")
    adversarial = load("adversarial.json")
    prompt_injection = load("prompt_injection.json")
    latency = load("latency_breakdown_ollama_steady_state.json")
    load_test = load("load-latest.json")

    metrics = (after or {}).get("metrics", {})
    leak_detail = (after or {}).get("permission_leakage_detail")

    cache_hit_rate = None
    if load_test:
        warm_rates = [
            p["cache_hit_rate"]
            for p in load_test.get("phases", [])
            if p.get("name", "").endswith("_warm") and p.get("cache_hit_rate") is not None
        ]
        if warm_rates:
            cache_hit_rate = round(sum(warm_rates) / len(warm_rates), 3)

    total_stage = (latency or {}).get("total", {})

    return EvalHeadline(
        total_questions=(after or {}).get("dataset_size"),
        answer_accuracy=metrics.get("answer_accuracy"),
        retrieval_hit_rate=metrics.get("retrieval_hit_rate"),
        citation_accuracy=metrics.get("citation_grounding"),
        citation_coverage=metrics.get("citation_coverage"),
        conflict_detection_accuracy=metrics.get("conflict_detection_accuracy"),
        refusal_accuracy=metrics.get("refusal_accuracy"),
        permission_leakage=metrics.get("permission_leakage")
        if metrics.get("permission_leakage") is not None
        else (0 if leak_detail and leak_detail.get("pass") else None),
        avg_latency_ms=total_stage.get("mean_ms"),
        p95_latency_ms=total_stage.get("p95_ms"),
        cache_hit_rate=cache_hit_rate,
        adversarial_passed=(adversarial or {}).get("passed"),
        adversarial_total=(adversarial or {}).get("total"),
        prompt_injection_passed=(prompt_injection or {}).get("passed"),
        prompt_injection_total=(prompt_injection or {}).get("total"),
        source_files=found,
        missing_files=missing,
    )


@router.get("/evals")
def evals(
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> dict[str, Any]:
    """Return the most recent eval run plus the T9.8 headline metrics picture,
    or a not-available marker.

    Eval results are a repo/CI artifact written by the eval/ scripts; this
    endpoint surfaces whatever they last produced. ``headline`` is assembled
    fresh from every eval/results/*.json file found on disk (see
    ``_build_headline``) — it is never hand-typed, so re-running any T9.1-T9.5
    script and refreshing this page always reflects the latest real numbers.
    """
    results_dir = _eval_results_dir()
    path = Path(settings.eval_results_path)
    if not path.exists():
        headline = _build_headline(results_dir)
        return {"available": False, "headline": headline.model_dump()}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Eval results exist but could not be read: {exc}",
        )
    data["available"] = True
    data["headline"] = _build_headline(results_dir).model_dump()
    return data


@router.get("/content-gaps", response_model=ContentGapsResponse)
def content_gaps(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> ContentGapsResponse:
    """Clusters of questions the assistant couldn't answer → Fog-of-War patches."""
    resolved = set(
        db.scalars(
            select(ContentGapResolution.gap_key).where(
                ContentGapResolution.workspace_id == principal.workspace_id
            )
        ).all()
    )
    gaps = compute_gaps(db, principal.workspace_id, resolved)
    return ContentGapsResponse(gaps=[ContentGap(**vars(g)) for g in gaps])


@router.post("/content-gaps/{gap_key}/resolve", response_model=ContentGapsResponse)
def resolve_content_gap(
    gap_key: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> ContentGapsResponse:
    """Mark a gap cluster resolved (clears its fog). Idempotent."""
    exists = db.scalar(
        select(ContentGapResolution).where(
            ContentGapResolution.workspace_id == principal.workspace_id,
            ContentGapResolution.gap_key == gap_key,
        )
    )
    if exists is None:
        db.add(
            ContentGapResolution(
                workspace_id=principal.workspace_id,
                gap_key=gap_key,
                resolved_by=principal.user_id,
            )
        )
        db.commit()
    resolved = set(
        db.scalars(
            select(ContentGapResolution.gap_key).where(
                ContentGapResolution.workspace_id == principal.workspace_id
            )
        ).all()
    )
    gaps = compute_gaps(db, principal.workspace_id, resolved)
    return ContentGapsResponse(gaps=[ContentGap(**vars(g)) for g in gaps])


@router.get("/query-volume", response_model=QueryVolumeResponse)
def query_volume(
    days: int = 14,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> QueryVolumeResponse:
    """Daily count of user questions over the last N days (feeds Trade Winds)."""
    days = max(1, min(90, days))
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(
            func.date(Message.created_at).label("d"),
            func.count().label("c"),
        )
        .where(
            Message.workspace_id == principal.workspace_id,
            Message.role == "user",
            Message.created_at >= since,
        )
        .group_by(func.date(Message.created_at))
        .order_by(func.date(Message.created_at))
    ).all()
    points = [QueryVolumePoint(date=str(d), count=int(c)) for d, c in rows]
    return QueryVolumeResponse(points=points)


@router.get("/audit-log", response_model=AuditLogResponse)
def audit_log(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> AuditLogResponse:
    """Tenant-scoped admin/editor action history — the read side of the
    ``app.audit.record()`` write path already wired into uploads, ACL changes,
    and workspace membership. Newest first."""
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    tenant = principal.workspace_id

    total = db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.workspace_id == tenant)
    )
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.workspace_id == tenant)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AuditLogResponse(
        entries=[AuditLogEntryOut.model_validate(r) for r in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/feedback", response_model=FeedbackSummaryResponse)
def feedback_summary(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_role(ROLE_ADMIN)),
) -> FeedbackSummaryResponse:
    """Every rated answer in the workspace — the read side of the feedback
    loop. Each assistant message's preceding user question (if any) is included
    for context, since a bare answer with no question is hard to judge."""
    tenant = principal.workspace_id

    rows = db.execute(
        select(MessageFeedback, Message, Conversation, User)
        .join(Message, MessageFeedback.message_id == Message.id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(User, MessageFeedback.user_id == User.id)
        .where(MessageFeedback.workspace_id == tenant)
        .order_by(MessageFeedback.created_at.desc())
    ).all()

    entries: list[FeedbackSummary] = []
    up_count = down_count = 0
    for fb, msg, convo, user in rows:
        if fb.rating == "up":
            up_count += 1
        else:
            down_count += 1
        prior_question = db.scalar(
            select(Message.content)
            .where(
                Message.conversation_id == convo.id,
                Message.role == "user",
                Message.created_at <= msg.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        entries.append(
            FeedbackSummary(
                message_id=msg.id,
                conversation_id=convo.id,
                question=prior_question,
                answer=msg.content,
                rating=fb.rating,
                user_email=user.email,
                created_at=fb.created_at,
            )
        )
    return FeedbackSummaryResponse(entries=entries, up_count=up_count, down_count=down_count)
