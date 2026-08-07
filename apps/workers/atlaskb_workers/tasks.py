"""Celery tasks. The ingestion task reuses the shared pipeline in ``app.ingest``."""

from app.ingest import ingest_document

from atlaskb_workers.celery_app import celery_app


@celery_app.task(name="atlaskb.ping")
def ping() -> str:
    """Trivial task to confirm the worker executes jobs."""
    return "pong"


@celery_app.task(name="atlaskb.ingest_document")
def ingest_document_task(document_id: str) -> None:
    """Parse -> chunk -> embed -> write chunks for one uploaded document."""
    ingest_document(document_id)
