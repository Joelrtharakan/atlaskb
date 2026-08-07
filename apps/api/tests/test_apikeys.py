"""API key lifecycle and use as an alternative auth method."""

from __future__ import annotations

import io


def _upload(client, headers):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": ("d.md", io.BytesIO(b"# D\n\nMars is the Red Planet.\n"), "text/markdown")},
    )


def test_create_lists_and_reveals_key_once(client, make_user):
    user = make_user()
    created = client.post("/api-keys", headers=user.headers, json={"name": "ci"})
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("atlk_")  # plaintext, shown once
    assert body["role"] == "admin"  # inherits creator's role in personal tenant

    listed = client.get("/api-keys", headers=user.headers).json()
    assert len(listed) == 1
    assert "key" not in listed[0]  # never returned again
    assert listed[0]["lookup"] == body["lookup"]


def test_key_authenticates_search_and_chat(client, make_user, ingest_inline, stub_llm):
    user = make_user()
    _upload(client, user.headers)
    key = client.post("/api-keys", headers=user.headers, json={"name": "ci"}).json()["key"]
    hdr = {"X-API-Key": key}

    s = client.post("/search", headers=hdr, json={"query": "Mars"})
    assert s.status_code == 200
    assert any("Mars" in c["text"] for c in s.json()["results"])

    c = client.post("/chat", headers=hdr, json={"question": "What is Mars?"})
    assert c.status_code == 200
    assert c.json()["answerable"] is True


def test_revoked_key_is_rejected(client, make_user):
    user = make_user()
    created = client.post("/api-keys", headers=user.headers, json={"name": "ci"}).json()
    key, key_id = created["key"], created["id"]

    assert client.post("/search", headers={"X-API-Key": key}, json={"query": "x"}).status_code == 200
    assert client.delete(f"/api-keys/{key_id}", headers=user.headers).status_code == 204
    # After revocation the key no longer authenticates.
    assert client.post("/search", headers={"X-API-Key": key}, json={"query": "x"}).status_code == 401


def test_invalid_key_rejected(client):
    r = client.post("/search", headers={"X-API-Key": "atlk_not-a-real-key"}, json={"query": "x"})
    assert r.status_code == 401


def test_key_role_cannot_exceed_creator_role(client, make_user):
    admin = make_user()
    viewer = make_user()
    client.post(
        f"/workspaces/{admin.tenant_id}/invite",
        headers=admin.headers,
        json={"email": viewer.email, "role": "viewer"},
    )
    viewer_hdr = {**viewer.headers, "X-Tenant-Id": admin.tenant_id}

    # A viewer cannot mint an admin key...
    r = client.post("/api-keys", headers=viewer_hdr, json={"name": "k", "role": "admin"})
    assert r.status_code == 403
    # ...but can mint a viewer key.
    ok = client.post("/api-keys", headers=viewer_hdr, json={"name": "k", "role": "viewer"})
    assert ok.status_code == 201
    assert ok.json()["role"] == "viewer"


def test_cannot_create_key_using_a_key(client, make_user):
    user = make_user()
    key = client.post("/api-keys", headers=user.headers, json={"name": "ci"}).json()["key"]
    r = client.post("/api-keys", headers={"X-API-Key": key}, json={"name": "second"})
    assert r.status_code == 403
