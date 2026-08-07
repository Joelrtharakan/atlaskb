"""Thin Celery producer used by the API to enqueue ingestion jobs.

The API doesn't import worker code; it sends a task by name onto the shared
Redis broker. The worker (apps/workers) registers a task with the same name.
"""

from __future__ import annotations

from celery import Celery

from app.config import settings

INGEST_TASK = "atlaskb.ingest_document"

celery_producer = Celery("atlaskb-api", broker=settings.redis_url, backend=settings.redis_url)
celery_producer.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


def enqueue_ingest(document_id: str) -> None:
    celery_producer.send_task(INGEST_TASK, args=[document_id])
