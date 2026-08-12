"""Celery tasks. The ingestion task reuses the shared pipeline in ``app.ingest``."""

from app.connectors import connector_from_config, run_connector_sync
from app.db import SessionLocal
from app.ingest import ingest_document
from app.logging_config import get_logger
from app.models import ConnectorConfig

from atlaskb_workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="atlaskb.ping")
def ping() -> str:
    """Trivial task to confirm the worker executes jobs."""
    return "pong"


@celery_app.task(name="atlaskb.ingest_document")
def ingest_document_task(document_id: str) -> None:
    """Parse -> chunk -> embed -> write chunks for one uploaded document."""
    ingest_document(document_id)


@celery_app.task(name="atlaskb.sync_connector")
def sync_connector_task(connector_id: str, owner_id: str) -> None:
    """"Sync now" from Admin > Connectors — runs off the request thread so
    a large Drive folder doesn't hold the API request open. Only Google
    Drive exists as a real provider today; ``config.provider`` values other
    than "google_drive" have nothing to build here yet."""
    db = SessionLocal()
    try:
        config = db.get(ConnectorConfig, connector_id)
        if config is None:
            log.warning("connector.sync_task_missing_config", connector_id=connector_id)
            return
        if config.provider != "google_drive":
            log.warning("connector.sync_task_unsupported_provider", provider=config.provider)
            return
        connector = connector_from_config(config)
        run_connector_sync(db, connector, config, owner_id=owner_id)
    finally:
        db.close()
