"""Celery application, configured against Redis as broker.

No real jobs are defined yet (scaffold phase) — see ``tasks.py`` for the single
placeholder task used to verify the worker boots and can execute work.
"""

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

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
