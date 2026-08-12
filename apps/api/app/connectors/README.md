# Connector architecture (Trust Layer Phase 10 + 11)

Phase 10 built the abstraction (`Connector`, `run_connector_sync`,
`ConnectorConfig`/`ConnectorDocument`), proven only against an
explicitly-test-only fake connector — no real provider shipped, since a
working Google Drive connector needs a real OAuth app registration and
credentials that only the AtlasKB deployer can provide.

Phase 11 ships that real provider: `google_drive.py`'s `GoogleDriveConnector`,
a real OAuth flow (`app/routers/connectors.py`), encrypted refresh-token
storage (`tokens.py`), and a manual "Sync now" trigger from
`Admin > Connectors` in the web app. See `google_drive.py`'s module
docstring for the scope choices made in this first version (workspace-wide
visibility for synced files, no scheduler, `modifiedTime`-based change
detection).

## What exists

- `base.py` — the `Connector` abstract class (`authenticate`,
  `test_connection`, `list_sources`, `fetch_document`, `fetch_changes`,
  `delete_document`, `get_permissions`, plus a default `sync()` built from
  those) and the data shapes (`ExternalSource`, `NormalizedDocument`,
  `ExternalChange`, `ExternalPermissions`, `SyncResult`).
- `sync.py` — `run_connector_sync()`, which lists a connector's sources,
  fetches each, and hands the normalized bytes to the **exact same**
  ingestion pipeline direct upload already uses
  (`app.versioning.create_pending_version` + `app.ingest.ingest_document`)
  — no parsing/chunking/embedding logic is duplicated. Tracks per-document
  sync state in `ConnectorDocument` (checksum-based skip of unchanged
  documents, per-document error isolation so one bad fetch doesn't abort
  the whole sync).
- `google_drive.py` — `GoogleDriveConnector`, the real provider
  implementation against the Google Drive v3 API, including native
  Google Docs/Sheets/Slides export to a format `app.chunking` already
  parses.
- `tokens.py` — encrypts/decrypts each connector's refresh token
  (Fernet, keyed by `CONNECTOR_TOKEN_KEY`) before it's stored in
  `ConnectorConfig.credentials_ref`.
- `app.routers.connectors` — OAuth authorize/callback, connector
  CRUD, test-connection, and sync-now endpoints.
- `app.models.ConnectorConfig` / `ConnectorDocument` (migration
  `0009_connectors.py`) — the metadata schema: workspace, provider,
  external ids, last sync time/status, checksum, external version,
  permission metadata. `credentials_ref` holds the *encrypted* refresh
  token for Google Drive connectors — never plaintext.

## Deliberately out of scope for this pass

- **Permission mapping**: `GoogleDriveConnector.get_permissions()` always
  reports "not restricted" — every synced file is visible workspace-wide in
  AtlasKB, regardless of its Drive-level sharing. Mapping real per-file
  Drive ACLs onto AtlasKB's role/grant model is real, security-sensitive
  design work of its own (the two permission systems don't correspond
  1:1) — deferred, not defaulted-and-forgotten.
- **Scheduled sync**: only a manual "Sync now" trigger exists (an admin
  clicking a button in `Admin > Connectors`, which enqueues a Celery task).
  No Celery beat periodic task or Drive push-notification webhook — add one
  if/when auto-sync is actually wanted.
- **Change detection**: `fetch_changes()` uses a `modifiedTime` query,
  not Drive's `changes` page-token API — simpler and sufficient for
  on-demand syncs, but it won't detect a file moved out of the configured
  folder (only explicit trash counts as "deleted").

## What proves this works

`apps/api/tests/test_connectors.py`'s `_FakeConnector` (in-memory, no
network) exercises `run_connector_sync()` end-to-end against the real
ingestion pipeline — this is what proves the *architecture* works, and
still passes unchanged. `GoogleDriveConnector` itself has no automated
test double for the real Drive API (mocking Google's client wouldn't prove
much beyond "the mock returns what the mock returns"); it's exercised by
live-connecting a real Google account through `Admin > Connectors`.
