"""Generic connector abstraction (Trust Layer Phase 10).

See ``base.py`` for the ``Connector`` interface every provider implements,
and ``sync.py`` for how a connector's output reaches the existing
ingestion pipeline. No real provider (Google Drive, GitHub, Slack, ...)
ships in this phase — see ``base.py``'s module docstring for why.
"""

from .base import (
    Connector,
    ConnectorError,
    ExternalChange,
    ExternalPermissions,
    ExternalSource,
    NormalizedDocument,
    SyncResult,
)
from .google_drive import GoogleDriveConnector, GoogleDriveCredentials, connector_from_config
from .sync import run_connector_sync

__all__ = [
    "Connector",
    "ConnectorError",
    "ExternalChange",
    "ExternalPermissions",
    "ExternalSource",
    "GoogleDriveConnector",
    "GoogleDriveCredentials",
    "NormalizedDocument",
    "SyncResult",
    "connector_from_config",
    "run_connector_sync",
]
