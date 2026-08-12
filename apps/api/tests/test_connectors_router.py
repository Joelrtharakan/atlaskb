"""HTTP layer for connector management + Google Drive OAuth (Trust Layer
Phase 11), as distinct from tests/test_connectors.py's coverage of the
generic sync architecture itself (run_connector_sync + the fake connector).
No real Google API calls are made here -- the OAuth exchange and Drive API
client are monkeypatched, the same way test_oidc.py fakes an IdP's JWKS
rather than hitting a real one.
"""

from __future__ import annotations

from app.connectors import ConnectorError
from app.db import SessionLocal
from app.models import ConnectorConfig, ConnectorDocument
from app.routers.connectors import _normalize_folder_id


def _make_connector_config(workspace_id: str, *, connected: bool = True) -> str:
    db = SessionLocal()
    try:
        config = ConnectorConfig(
            workspace_id=workspace_id,
            provider="google_drive",
            name="Test Drive",
            credentials_ref="encrypted-blob" if connected else None,
            status="active",
        )
        db.add(config)
        db.commit()
        return config.id
    finally:
        db.close()


# --- _normalize_folder_id ---


def test_normalize_folder_id_extracts_id_from_full_url():
    url = "https://drive.google.com/drive/folders/15CE9dXJv1crS4fGDByWwgffjUicL4JuM?usp=sharing"
    assert _normalize_folder_id(url) == "15CE9dXJv1crS4fGDByWwgffjUicL4JuM"


def test_normalize_folder_id_passes_through_bare_id():
    assert _normalize_folder_id("15CE9dXJv1crS4fGDByWwgffjUicL4JuM") == "15CE9dXJv1crS4fGDByWwgffjUicL4JuM"


def test_normalize_folder_id_none_and_empty():
    assert _normalize_folder_id(None) is None
    assert _normalize_folder_id("") is None
    assert _normalize_folder_id("   ") == ""  # whitespace-only strips to empty, not None -- not a realistic input


# --- GET /connectors ---


def test_list_connectors_empty_for_new_workspace(client, make_user):
    user = make_user()
    r = client.get("/connectors", headers=user.headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_connectors_admin_only(client, make_user, grant_membership):
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")

    r = client.get("/connectors", headers=viewer.in_ws(admin.workspace_id))
    assert r.status_code == 403


def test_list_connectors_scoped_to_workspace(client, make_user):
    a = make_user()
    b = make_user()
    _make_connector_config(a.workspace_id)

    r = client.get("/connectors", headers=b.headers)
    assert r.status_code == 200
    assert r.json() == []


# --- POST /connectors/google/authorize ---


def test_authorize_503_when_google_not_configured(client, make_user, monkeypatch):
    monkeypatch.setattr("app.routers.connectors.settings.google_client_id", "")
    admin = make_user()
    r = client.post(
        "/connectors/google/authorize", headers=admin.headers, json={"name": "My Drive", "folder_id": None}
    )
    assert r.status_code == 503


def test_authorize_returns_google_url_when_configured(client, make_user, monkeypatch):
    monkeypatch.setattr("app.routers.connectors.settings.google_client_id", "fake-client-id")
    monkeypatch.setattr("app.routers.connectors.settings.google_client_secret", "fake-secret")
    admin = make_user()
    r = client.post(
        "/connectors/google/authorize", headers=admin.headers, json={"name": "My Drive", "folder_id": None}
    )
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/auth")
    assert "state=" in url
    assert "code_challenge=" in url  # PKCE


def test_authorize_normalizes_pasted_folder_url_into_state(client, make_user, monkeypatch):
    import jwt as pyjwt
    from app.config import settings

    monkeypatch.setattr("app.routers.connectors.settings.google_client_id", "fake-client-id")
    monkeypatch.setattr("app.routers.connectors.settings.google_client_secret", "fake-secret")
    admin = make_user()
    r = client.post(
        "/connectors/google/authorize",
        headers=admin.headers,
        json={"name": "My Drive", "folder_id": "https://drive.google.com/drive/folders/ABC123?usp=sharing"},
    )
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    state = url.split("state=")[1].split("&")[0]
    payload = pyjwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert payload["folder_id"] == "ABC123"


def test_authorize_requires_admin(client, make_user, grant_membership, monkeypatch):
    monkeypatch.setattr("app.routers.connectors.settings.google_client_id", "fake-client-id")
    monkeypatch.setattr("app.routers.connectors.settings.google_client_secret", "fake-secret")
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "editor")

    r = client.post(
        "/connectors/google/authorize",
        headers=viewer.in_ws(admin.workspace_id),
        json={"name": "My Drive", "folder_id": None},
    )
    assert r.status_code == 403


# --- GET /connectors/google/callback ---


def test_callback_redirects_with_error_on_invalid_state(client):
    r = client.get(
        "/connectors/google/callback", params={"code": "abc", "state": "not-a-real-jwt"}, follow_redirects=False
    )
    assert r.status_code == 307
    assert "error=invalid_state" in r.headers["location"]


def test_callback_redirects_with_error_when_exchange_fails(client, make_user, monkeypatch):
    monkeypatch.setattr("app.routers.connectors.settings.google_client_id", "fake-client-id")
    monkeypatch.setattr("app.routers.connectors.settings.google_client_secret", "fake-secret")
    admin = make_user()
    authorize = client.post(
        "/connectors/google/authorize", headers=admin.headers, json={"name": "My Drive", "folder_id": None}
    )
    state = authorize.json()["authorize_url"].split("state=")[1].split("&")[0]

    # No real Google token endpoint to talk to -- fetch_token() will fail
    # against a fake auth code, which must redirect with an error, never 500.
    r = client.get(
        "/connectors/google/callback", params={"code": "not-a-real-code", "state": state}, follow_redirects=False
    )
    assert r.status_code == 307
    assert "error=" in r.headers["location"]


# --- POST /connectors/{id}/sync ---


def test_sync_now_404_for_unknown_connector(client, make_user):
    admin = make_user()
    r = client.post("/connectors/00000000-0000-0000-0000-000000000000/sync", headers=admin.headers)
    assert r.status_code == 404


def test_sync_now_404_for_other_workspace_connector(client, make_user):
    a = make_user()
    b = make_user()
    connector_id = _make_connector_config(a.workspace_id)

    r = client.post(f"/connectors/{connector_id}/sync", headers=b.headers)
    assert r.status_code == 404


def test_sync_now_409_when_not_connected(client, make_user):
    admin = make_user()
    connector_id = _make_connector_config(admin.workspace_id, connected=False)

    r = client.post(f"/connectors/{connector_id}/sync", headers=admin.headers)
    assert r.status_code == 409


def test_sync_now_queues_when_connected(client, make_user, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.routers.connectors.enqueue_connector_sync", lambda cid, uid: calls.append((cid, uid))
    )
    admin = make_user()
    connector_id = _make_connector_config(admin.workspace_id, connected=True)

    r = client.post(f"/connectors/{connector_id}/sync", headers=admin.headers)
    assert r.status_code == 202
    assert r.json() == {"queued": True}
    assert calls == [(connector_id, admin.user_id)]


# --- POST /connectors/{id}/test ---


class _FakeConnectorOK:
    def authenticate(self):
        pass

    def test_connection(self):
        return True


class _FakeConnectorAuthFails:
    def authenticate(self):
        raise ConnectorError("refresh token revoked")

    def test_connection(self):  # pragma: no cover - never reached
        return False


def test_test_connection_409_when_not_connected(client, make_user):
    admin = make_user()
    connector_id = _make_connector_config(admin.workspace_id, connected=False)

    r = client.post(f"/connectors/{connector_id}/test", headers=admin.headers)
    assert r.status_code == 409


def test_test_connection_ok(client, make_user, monkeypatch):
    monkeypatch.setattr("app.routers.connectors.connector_from_config", lambda config: _FakeConnectorOK())
    admin = make_user()
    connector_id = _make_connector_config(admin.workspace_id, connected=True)

    r = client.post(f"/connectors/{connector_id}/test", headers=admin.headers)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_test_connection_reports_connector_error_without_500(client, make_user, monkeypatch):
    monkeypatch.setattr(
        "app.routers.connectors.connector_from_config", lambda config: _FakeConnectorAuthFails()
    )
    admin = make_user()
    connector_id = _make_connector_config(admin.workspace_id, connected=True)

    r = client.post(f"/connectors/{connector_id}/test", headers=admin.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "revoked" in body["error"]


# --- DELETE /connectors/{id} ---


def test_delete_connector_404_for_other_workspace(client, make_user):
    a = make_user()
    b = make_user()
    connector_id = _make_connector_config(a.workspace_id)

    r = client.delete(f"/connectors/{connector_id}", headers=b.headers)
    assert r.status_code == 404


def test_delete_connector_cascades_connector_documents(client, make_user):
    admin = make_user()
    connector_id = _make_connector_config(admin.workspace_id)

    db = SessionLocal()
    try:
        db.add(
            ConnectorDocument(
                connector_id=connector_id,
                workspace_id=admin.workspace_id,
                external_source_id="google_drive",
                external_document_id="file-1",
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.delete(f"/connectors/{connector_id}", headers=admin.headers)
    assert r.status_code == 204

    db = SessionLocal()
    try:
        assert db.get(ConnectorConfig, connector_id) is None
        assert db.query(ConnectorDocument).filter_by(connector_id=connector_id).count() == 0
    finally:
        db.close()


def test_delete_connector_requires_admin(client, make_user, grant_membership):
    admin = make_user()
    editor = make_user(create_workspace=False)
    grant_membership(editor.user_id, admin.workspace_id, "editor")
    connector_id = _make_connector_config(admin.workspace_id)

    r = client.delete(f"/connectors/{connector_id}", headers=editor.in_ws(admin.workspace_id))
    assert r.status_code == 403
