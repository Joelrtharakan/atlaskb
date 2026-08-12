"""Real Google Drive connector (Trust Layer Phase 11).

Implements the ``Connector`` interface from ``base.py`` against the actual
Google Drive API. Unlike ``tests/test_connectors.py``'s ``_FakeConnector``,
this talks to a real Google account and needs real OAuth credentials that
only the workspace owner can provide (see ``app/routers/connectors.py`` for
the authorize/callback flow that produces them) — there is no way to
exercise this class without a real Google Cloud OAuth client and a real
Drive account to connect.

Scope choices for this first version (tracked so a future pass knows what
was deliberately deferred, not accidentally missed):
  * Permissions: ``get_permissions`` always reports "not restricted" — every
    synced file is visible workspace-wide in AtlasKB regardless of its Drive
    sharing. Mapping real per-file Drive ACLs onto AtlasKB's grant model is
    out of scope for this pass (see ``ExternalPermissions``'s docstring).
  * Sync trigger: this connector has no scheduler awareness of its own;
    ``fetch_changes`` is called only when something else (the "Sync now"
    endpoint) decides to call it — there's no polling loop here.
  * ``fetch_changes`` uses a ``modifiedTime`` query rather than Drive's
    ``changes`` page-token API — simpler and sufficient for manual,
    on-demand syncs; it doesn't detect files moved outside the configured
    folder (`trashed=true` covers explicit deletes only, not that case).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.config import settings

from .base import (
    Connector,
    ConnectorError,
    ExternalChange,
    ExternalPermissions,
    ExternalSource,
    NormalizedDocument,
)
from .tokens import decrypt_credentials

if TYPE_CHECKING:
    from app.models import ConnectorConfig

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Native Google formats aren't fetchable as raw bytes — they must be exported
# to a format app.chunking already knows how to parse (see
# app/connectors/sync.py's _EXT_BY_CONTENT_TYPE: pdf/markdown/html only).
_EXPORT_MIME_BY_GOOGLE_TYPE = {
    "application/vnd.google-apps.document": ("text/html", ".html"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/plain", ".txt"),
}
# app.chunking has no CSV/plain-text parser; sync.py's _extension_for
# already falls back to ".md" for any content type/extension it doesn't
# recognize (including "text/csv" and ".txt"), so CSV/slide-text exports
# are read as markdown-ish plain text without any extra mapping here.

_LIST_FIELDS = "nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum, trashed)"


@dataclass
class GoogleDriveCredentials:
    """What's needed to (re)build an authenticated Drive client — the
    refresh token comes from the OAuth callback, decrypted by
    ``app.connectors.tokens`` just before constructing this connector; it is
    never held anywhere longer-lived than one sync's in-memory connector
    instance."""

    refresh_token: str
    client_id: str
    client_secret: str


class GoogleDriveConnector(Connector):
    def __init__(self, credentials: GoogleDriveCredentials, *, folder_id: str | None = None):
        """``folder_id``: restrict sync to one Drive folder (recommended —
        an unset folder_id syncs every file the connected account can read,
        which for a personal/workspace Drive can be a lot). Set from
        ``ConnectorConfig`` by the caller, not stored on this class beyond
        construction."""
        self._creds_input = credentials
        self._folder_id = folder_id
        self._creds: Credentials | None = None
        self._service = None

    def authenticate(self) -> None:
        creds = Credentials(
            token=None,
            refresh_token=self._creds_input.refresh_token,
            token_uri=TOKEN_URI,
            client_id=self._creds_input.client_id,
            client_secret=self._creds_input.client_secret,
            scopes=SCOPES,
        )
        try:
            creds.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            raise ConnectorError(f"Google Drive re-authentication failed: {exc}") from exc
        self._creds = creds
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def test_connection(self) -> bool:
        if self._service is None:
            return False
        try:
            self._service.about().get(fields="user").execute()
            return True
        except HttpError:
            return False

    def _query(self, extra: str | None = None) -> str:
        clauses = ["trashed = false", "mimeType != 'application/vnd.google-apps.folder'"]
        if self._folder_id:
            clauses.append(f"'{self._folder_id}' in parents")
        if extra:
            clauses.append(extra)
        return " and ".join(clauses)

    def _list_files(self, query: str) -> list[dict]:
        files: list[dict] = []
        page_token = None
        while True:
            resp = (
                self._service.files()
                .list(q=query, fields=_LIST_FIELDS, pageSize=200, pageToken=page_token, spaces="drive")
                .execute()
            )
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return files

    def list_sources(self) -> list[ExternalSource]:
        files = self._list_files(self._query())
        return [
            ExternalSource(
                external_id=f["id"],
                name=f["name"],
                external_version=f.get("modifiedTime"),
                last_modified=_parse_rfc3339(f.get("modifiedTime")),
            )
            for f in files
        ]

    def fetch_document(self, external_id: str) -> NormalizedDocument:
        meta = (
            self._service.files()
            .get(fileId=external_id, fields="id, name, mimeType, modifiedTime, md5Checksum")
            .execute()
        )
        mime_type = meta["mimeType"]
        export = _EXPORT_MIME_BY_GOOGLE_TYPE.get(mime_type)
        buf = io.BytesIO()
        if export is not None:
            export_mime, ext = export
            request = self._service.files().export_media(fileId=external_id, mimeType=export_mime)
            content_type = export_mime
        else:
            request = self._service.files().get_media(fileId=external_id)
            content_type = mime_type
            ext = ""
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        content = buf.getvalue()

        filename = meta["name"] + ext if export is not None and not meta["name"].endswith(ext) else meta["name"]
        return NormalizedDocument(
            external_id=external_id,
            filename=filename,
            content_type=content_type,
            content=content,
            external_version=meta.get("modifiedTime"),
            checksum=meta.get("md5Checksum"),
        )

    def fetch_changes(self, since: datetime | None) -> list[ExternalChange]:
        if since is None:
            return [
                ExternalChange(external_id=s.external_id, change_type="modified", external_version=s.external_version)
                for s in self.list_sources()
            ]
        since_iso = since.astimezone().isoformat()
        modified = self._list_files(self._query(f"modifiedTime > '{since_iso}'"))
        deleted_clauses = ["trashed = true", f"modifiedTime > '{since_iso}'"]
        if self._folder_id:
            deleted_clauses.append(f"'{self._folder_id}' in parents")
        deleted = self._list_files(" and ".join(deleted_clauses))
        changes = [
            ExternalChange(external_id=f["id"], change_type="modified", external_version=f.get("modifiedTime"))
            for f in modified
        ]
        changes += [ExternalChange(external_id=f["id"], change_type="deleted") for f in deleted]
        return changes

    def delete_document(self, external_id: str) -> None:
        # Drive is the source of truth; AtlasKB never deletes the user's own
        # Drive file. Removing AtlasKB's copy is sync.py's job via the normal
        # document lifecycle, not this method (see Connector.delete_document
        # docstring in base.py).
        return None

    def get_permissions(self, external_id: str) -> ExternalPermissions:
        # v1 scope: workspace-wide visibility for every synced file,
        # regardless of Drive-level sharing — see module docstring.
        return ExternalPermissions(external_id=external_id, is_restricted=False, raw={})


def connector_from_config(config: ConnectorConfig) -> GoogleDriveConnector:
    """Rebuilds a ``GoogleDriveConnector`` from a stored ``ConnectorConfig``
    row — decrypts ``credentials_ref`` in-memory only for the duration of
    the caller's sync, never persists the plaintext refresh token anywhere
    beyond this call. The one place both the OAuth callback (which writes
    ``credentials_ref``) and the sync task (which reads it back) agree on
    its shape: ``{"refresh_token": ..., "folder_id": ...}``."""
    if config.credentials_ref is None:
        raise ConnectorError(f"connector {config.id} has no stored credentials — reconnect it.")
    data = decrypt_credentials(config.credentials_ref)
    return GoogleDriveConnector(
        GoogleDriveCredentials(
            refresh_token=data["refresh_token"],
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        ),
        folder_id=data.get("folder_id"),
    )


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
