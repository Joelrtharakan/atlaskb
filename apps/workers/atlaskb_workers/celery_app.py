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
)
