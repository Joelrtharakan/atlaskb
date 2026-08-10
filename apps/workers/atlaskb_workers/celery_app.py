"""Celery application, configured against Redis as broker.

Registered tasks live in ``tasks.py``; the main job is ``atlaskb.ingest_document``
(parse -> chunk -> embed -> write chunks) enqueued by the API on upload.
"""

# Reuse the API's settings so the worker reads the same .env / REDIS_URL and the
# API producer and worker consumer always agree on the broker.
from app.config import settings
from celery import Celery

REDIS_URL = settings.redis_url

celery_app = Celery(
    "atlaskb",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["atlaskb_workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Reliability: only ack a message after the task actually finishes, and if
    # the worker process dies mid-task (crash, OOM, kill -9), redeliver it to
    # another worker instead of silently dropping it. Safe here because
    # ingest_document is idempotent (delete-then-insert chunks) — a redelivered
    # task just re-does the same work rather than duplicating it.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # With acks_late, the default prefetch would let one worker hoard several
    # documents' jobs before finishing any of them; 1 keeps ingestion latency
    # predictable when multiple uploads land close together.
    worker_prefetch_multiplier=1,
)
