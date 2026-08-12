"""Connector architecture (Trust Layer Phase 10).

``_FakeConnector`` below is explicitly a test fixture, not a product
connector — it holds in-memory documents and talks to no real external
service. Its only job is to prove ``run_connector_sync`` correctly hands a
connector's output to the real ingestion pipeline end-to-end. No real
provider (Google Drive, GitHub, Slack, ...) exists in this codebase — see
app/connectors/README.md.
"""

from __future__ import annotations

from datetime import datetime

from app.connectors import (
    Connector,
    ConnectorError,
    ExternalChange,
    ExternalPermissions,
    ExternalSource,
    NormalizedDocument,
    run_connector_sync,
)
from app.db import SessionLocal
from app.models import ConnectorConfig, ConnectorDocument


class _FakeConnector(Connector):
    """In-memory, no network — a test fixture proving the abstraction and
    orchestration work, never a real provider."""

    def __init__(self, documents: dict[str, bytes], *, fail_auth: bool = False, fail_ids: set[str] | None = None):
        self._documents = documents
        self._fail_auth = fail_auth
        self._fail_ids = fail_ids or set()
        self.authenticated = False

    def authenticate(self) -> None:
        if self._fail_auth:
            raise ConnectorError("fake auth failure")
        self.authenticated = True

    def test_connection(self) -> bool:
        return self.authenticated

    def list_sources(self) -> list[ExternalSource]:
        return [ExternalSource(external_id=k, name=k) for k in self._documents]

    def fetch_document(self, external_id: str) -> NormalizedDocument:
        if external_id in self._fail_ids:
            raise RuntimeError(f"simulated fetch failure for {external_id}")
        content = self._documents[external_id]
        return NormalizedDocument(
            external_id=external_id, filename=f"{external_id}.md", content_type="text/markdown",
            content=content, checksum=str(hash(content)),
        )

    def fetch_changes(self, since: datetime | None) -> list[ExternalChange]:
        return [ExternalChange(external_id=k, change_type="modified") for k in self._documents]

    def delete_document(self, external_id: str) -> None:
        self._documents.pop(external_id, None)

    def get_permissions(self, external_id: str) -> ExternalPermissions:
        return ExternalPermissions(external_id=external_id, is_restricted=False)


def _make_config_id(workspace_id: str, provider: str = "fake") -> str:
    """Returns a plain id, not the ORM object — SQLAlchemy instances are
    tied to the session that loaded them, and callers each open their own
    session per ``run_connector_sync`` call (matching how a real Celery
    sync task would), so re-fetching by id in that session is required, not
    optional (a detached instance's mutations silently don't persist)."""
    db = SessionLocal()
    try:
        config = ConnectorConfig(workspace_id=workspace_id, provider=provider, name="test connector")
        db.add(config)
        db.commit()
        return config.id
    finally:
        db.close()


def _sync(config_id: str, connector: Connector, owner_id: str) -> None:
    db = SessionLocal()
    try:
        config = db.get(ConnectorConfig, config_id)
        run_connector_sync(db, connector, config, owner_id=owner_id)
    finally:
        db.close()


def test_connector_base_sync_calls_lifecycle_in_order():
    calls = []

    class _RecordingConnector(_FakeConnector):
        def authenticate(self):
            calls.append("authenticate")
            super().authenticate()

        def list_sources(self):
            calls.append("list_sources")
            return super().list_sources()

        def fetch_document(self, external_id):
            calls.append(f"fetch:{external_id}")
            return super().fetch_document(external_id)

    connector = _RecordingConnector({"a": b"# A\n", "b": b"# B\n"})
    result = connector.sync()
    assert calls[0] == "authenticate"
    assert calls[1] == "list_sources"
    assert result.synced == 2
    assert result.failed == 0


def test_connector_sync_isolates_per_document_failures():
    connector = _FakeConnector({"a": b"# A\n", "b": b"# B\n"}, fail_ids={"b"})
    result = connector.sync()
    assert result.synced == 1
    assert result.failed == 1
    assert "b" in result.errors[0]


def test_connector_auth_failure_raises():
    connector = _FakeConnector({}, fail_auth=True)
    try:
        connector.sync()
        raise AssertionError("expected ConnectorError")
    except ConnectorError:
        pass


def test_run_connector_sync_creates_and_ingests_real_document(client, make_user, ingest_inline):
    user = make_user()
    config_id = _make_config_id(user.workspace_id)
    connector = _FakeConnector({"doc-1": b"# Falcon Policy\n\nThe secret code is QUEBEC-9981.\n"})

    _sync(config_id, connector, user.user_id)

    r = client.get("/documents", headers=user.headers)
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) == 1
    assert docs[0]["source"] == "fake"
    assert docs[0]["status"] == "ready"

    db = SessionLocal()
    try:
        record = db.query(ConnectorDocument).filter_by(connector_id=config_id).one()
        assert record.sync_status == "ok"
        assert record.document_id == docs[0]["id"]
        assert record.checksum is not None

        refreshed_config = db.get(ConnectorConfig, config_id)
        assert refreshed_config.last_sync_status == "ok"
        assert refreshed_config.last_sync_at is not None
    finally:
        db.close()


def test_run_connector_sync_skips_unchanged_document_on_resync(client, make_user, ingest_inline):
    user = make_user()
    config_id = _make_config_id(user.workspace_id)
    connector = _FakeConnector({"doc-1": b"# Doc\n\nUnchanged content.\n"})

    _sync(config_id, connector, user.user_id)
    _sync(config_id, connector, user.user_id)

    r = client.get("/documents", headers=user.headers)
    # Second sync must not create a second Document for the same unchanged
    # external document.
    assert len(r.json()) == 1


def test_run_connector_sync_creates_new_version_on_changed_document(client, make_user, ingest_inline):
    user = make_user()
    config_id = _make_config_id(user.workspace_id)
    connector = _FakeConnector({"doc-1": b"# Doc\n\nVersion one.\n"})

    _sync(config_id, connector, user.user_id)

    connector._documents["doc-1"] = b"# Doc\n\nVersion two, changed.\n"
    _sync(config_id, connector, user.user_id)

    r = client.get("/documents", headers=user.headers)
    docs = r.json()
    assert len(docs) == 1  # still one Document row...
    versions = client.get(f"/documents/{docs[0]['id']}/versions", headers=user.headers).json()
    assert len(versions["versions"]) == 2  # ...but two real versions.


def test_run_connector_sync_auth_failure_marks_config_error_not_crash(client, make_user):
    user = make_user()
    config_id = _make_config_id(user.workspace_id)
    connector = _FakeConnector({}, fail_auth=True)

    _sync(config_id, connector, user.user_id)  # must not raise

    db = SessionLocal()
    try:
        refreshed = db.get(ConnectorConfig, config_id)
        assert refreshed.last_sync_status == "error"
    finally:
        db.close()


def test_run_connector_sync_isolates_per_document_failure_from_the_rest(
    client, make_user, ingest_inline
):
    user = make_user()
    config_id = _make_config_id(user.workspace_id)
    connector = _FakeConnector(
        {"good": b"# Good\n\nFine.\n", "bad": b"# Bad\n\nDoesn't matter.\n"}, fail_ids={"bad"}
    )

    _sync(config_id, connector, user.user_id)

    r = client.get("/documents", headers=user.headers)
    docs = r.json()
    assert len(docs) == 1
    assert docs[0]["status"] == "ready"

    db = SessionLocal()
    try:
        records = db.query(ConnectorDocument).filter_by(connector_id=config_id).all()
        statuses = {r.external_document_id: r.sync_status for r in records}
        assert statuses.get("good") == "ok"
        # "bad" never got far enough to create a ConnectorDocument row at
        # all (fetch failed before any record existed) -- confirmed absent,
        # not silently swallowed into a fake "ok".
        assert "bad" not in statuses
    finally:
        db.close()
