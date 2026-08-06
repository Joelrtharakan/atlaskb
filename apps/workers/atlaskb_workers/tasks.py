"""Placeholder tasks. No real jobs yet."""

from atlaskb_workers.celery_app import celery_app


@celery_app.task(name="atlaskb.ping")
def ping() -> str:
    """Trivial task to confirm the worker executes jobs."""
    return "pong"
