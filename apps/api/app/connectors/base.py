"""Generic connector abstraction (Trust Layer Phase 10).

A ``Connector`` is how an external source (Google Drive, GitHub, Slack, ...)
feeds documents into AtlasKB's existing ingestion pipeline. The contract is
deliberately narrow — every provider implements the same 8 methods, and
everything downstream (parse → chunk → embed → version → index → RAG) is
the pipeline that already exists for direct upload (``app.ingest``,
``app.versioning``). See ``sync.py`` for exactly how a connector's output is
handed off to that pipeline; a provider implementation never touches
ingestion internals directly.

This module is the architecture a real provider implements against, proven
end-to-end by tests using an explicitly-test-only fake connector (see
``apps/api/tests/test_connectors.py``). ``google_drive.py``'s
``GoogleDriveConnector`` is the first real provider built against it (Trust
Layer Phase 11) — see that module's docstring for what it does and what it
deliberately defers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExternalSource:
    """One document as the external provider sees it, before it's fetched."""

    external_id: str
    name: str
    external_version: str | None = None
    last_modified: datetime | None = None


@dataclass
class NormalizedDocument:
    """A fetched external document, normalized to what
    ``app.ingest``/``app.versioning`` already expect: raw bytes plus enough
    metadata to create a ``Document``/``DocumentVersion`` row. Content type
    follows the same values ``POST /documents`` already accepts."""

    external_id: str
    filename: str
    content_type: str
    content: bytes
    external_version: str | None = None
    checksum: str | None = None


@dataclass
class ExternalChange:
    """One entry from an incremental change feed — enough to know whether a
    previously-synced document needs re-fetching or removing, without
    fetching every document's full content on every sync."""

    external_id: str
    change_type: str  # "modified" | "deleted"
    external_version: str | None = None


@dataclass
class ExternalPermissions:
    """Coarse permission info for a connector-owned document — deliberately
    a placeholder shape (a real provider's ACL model rarely maps 1:1 onto
    AtlasKB's role/grant model), not translated into
    ``DocumentAccessGrant`` rows automatically. That mapping is real
    provider-specific work for whichever connector ships first, not
    something a generic abstraction can decide."""

    external_id: str
    is_restricted: bool
    raw: dict = field(default_factory=dict)


@dataclass
class SyncResult:
    synced: int
    failed: int
    skipped: int
    errors: list[str] = field(default_factory=list)


class ConnectorError(Exception):
    """Raised by a connector implementation on an unrecoverable failure
    (auth failure, unreachable API, etc.) — distinct from a per-document
    fetch failure, which a connector should instead surface via
    ``SyncResult.errors`` so one bad document doesn't abort an entire sync.
    """


class Connector(ABC):
    """One connector instance per ``ConnectorConfig`` row (one external
    account/workspace connection). Implementations must never accept or
    store plaintext credentials in source code — see
    ``ConnectorConfig.credentials_ref`` in ``app.models``."""

    @abstractmethod
    def authenticate(self) -> None:
        """Establish/refresh whatever session or token the provider's API
        needs. Raises ``ConnectorError`` on failure."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Cheap reachability + auth check, safe to call before a real sync
        (e.g. to validate a newly-configured connector in an admin UI)."""

    @abstractmethod
    def list_sources(self) -> list[ExternalSource]:
        """Every document this connector is configured to see, without
        fetching content — used to plan a sync, and to detect deletions by
        diffing against previously-synced ``ConnectorDocument`` rows."""

    @abstractmethod
    def fetch_document(self, external_id: str) -> NormalizedDocument:
        """Fetch one document's full content, normalized for the existing
        ingestion pipeline."""

    @abstractmethod
    def fetch_changes(self, since: datetime | None) -> list[ExternalChange]:
        """Incremental changes since a prior sync (``since=None`` means
        "since the beginning" — equivalent to a first full sync). Used for
        Phase 10's DoD requirement of both an initial and an incremental
        sync path, not just a full re-scan every time."""

    @abstractmethod
    def delete_document(self, external_id: str) -> None:
        """Best-effort notification to the provider side, if the provider
        supports it (many won't — deleting AtlasKB's own copy is
        ``sync.py``'s job, via the normal document lifecycle, not this
        method)."""

    @abstractmethod
    def get_permissions(self, external_id: str) -> ExternalPermissions:
        """Raw permission info for one document — see
        ``ExternalPermissions`` for why this isn't auto-translated into
        AtlasKB ACL grants."""

    def sync(self, since: datetime | None = None) -> SyncResult:
        """Default full-or-incremental sync loop, built from the abstract
        methods above — a provider only needs to override this if its API
        has a genuinely better bulk-sync primitive than "list then fetch
        each". See ``sync.run_connector_sync`` for the version that also
        writes results into AtlasKB's own ingestion pipeline; this method
        alone only talks to the external provider, so it's safe to unit
        test without a database."""
        self.authenticate()
        sources = (
            self.list_sources()
            if since is None
            else [
                ExternalSource(external_id=c.external_id, name=c.external_id, external_version=c.external_version)
                for c in self.fetch_changes(since)
                if c.change_type != "deleted"
            ]
        )
        synced, failed, errors = 0, 0, []
        for source in sources:
            try:
                self.fetch_document(source.external_id)
                synced += 1
            except Exception as exc:  # noqa: BLE001 - one bad document must not abort the sync
                failed += 1
                errors.append(f"{source.external_id}: {exc}")
        return SyncResult(synced=synced, failed=failed, skipped=0, errors=errors)
