"""Tenant isolation — the most important tests in this phase.

Every test here takes the perspective of an attacker in tenant B trying to reach
tenant A's data through some endpoint, and asserts they are rejected.
"""

from __future__ import annotations

import io

SECRET_MD = b"# Secret\n\nThe launch code for tenant A is ZULU-7788.\n"


def _upload(client, headers, body=SECRET_MD, name="secret.md"):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(body), "text/markdown")},
    )


def test_cannot_list_another_tenants_documents(client, make_user, ingest_inline):
    alice = make_user()
    bob = make_user()

    up = _upload(client, alice.headers)
    assert up.status_code == 201

    # Bob's document list (his own tenant) is empty; Alice's doc never appears.
    bob_docs = client.get("/documents", headers=bob.headers).json()
    assert bob_docs == []


def test_cannot_read_another_tenants_document_detail(client, make_user, ingest_inline):
    alice = make_user()
    bob = make_user()
    doc_id = _upload(client, alice.headers).json()["id"]

    # Bob (in his own tenant) gets 404 — existence is never revealed.
    assert client.get(f"/documents/{doc_id}", headers=bob.headers).status_code == 404
    # Alice can read her own.
    assert client.get(f"/documents/{doc_id}", headers=alice.headers).status_code == 200


def test_cannot_act_in_a_tenant_you_dont_belong_to(client, make_user):
    alice = make_user()
    bob = make_user()

    # Bob presents Alice's tenant id — he is not a member → 403.
    r = client.get("/documents", headers={**bob.headers, "X-Tenant-Id": alice.tenant_id})
    assert r.status_code == 403


def test_search_does_not_cross_tenants(client, make_user, ingest_inline):
    alice = make_user()
    bob = make_user()
    _upload(client, alice.headers)

    # Bob searches for Alice's secret content — retrieval is tenant-scoped.
    r = client.post("/search", headers=bob.headers, json={"query": "launch code ZULU-7788"})
    assert r.status_code == 200
    assert r.json()["results"] == []

    # Alice finds it in her own tenant.
    r2 = client.post("/search", headers=alice.headers, json={"query": "launch code ZULU-7788"})
    assert any("ZULU-7788" in c["text"] for c in r2.json()["results"])


def test_chat_does_not_leak_across_tenants(client, make_user, ingest_inline, stub_llm):
    alice = make_user()
    bob = make_user()
    _upload(client, alice.headers)

    # Bob asks about Alice's secret — no chunks are visible, so no answer.
    r = client.post("/chat", headers=bob.headers, json={"question": "What is the launch code?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answerable"] is False
    assert body["retrieved"] == []


def test_cannot_open_another_tenants_conversation(client, make_user, ingest_inline, stub_llm):
    alice = make_user()
    bob = make_user()
    _upload(client, alice.headers)

    convo_id = client.post(
        "/chat", headers=alice.headers, json={"question": "What is the launch code?"}
    ).json()["conversation_id"]
    assert convo_id

    # Bob cannot read Alice's conversation...
    assert client.get(f"/conversations/{convo_id}", headers=bob.headers).status_code == 404
    # ...nor continue it via /chat.
    r = client.post(
        "/chat",
        headers=bob.headers,
        json={"question": "and again?", "conversation_id": convo_id},
    )
    assert r.status_code == 404


def test_cannot_view_or_revoke_another_tenants_api_key(client, make_user):
    alice = make_user()
    bob = make_user()

    key_id = client.post(
        "/api-keys", headers=alice.headers, json={"name": "alice-key"}
    ).json()["id"]

    # Bob's listing (his tenant) doesn't include Alice's key.
    assert all(k["id"] != key_id for k in client.get("/api-keys", headers=bob.headers).json())
    # Bob cannot revoke it.
    assert client.delete(f"/api-keys/{key_id}", headers=bob.headers).status_code == 404


def test_api_key_is_scoped_to_its_tenant(client, make_user, ingest_inline):
    alice = make_user()
    bob = make_user()
    _upload(client, alice.headers)  # Alice's secret

    # Bob's API key can only see Bob's (empty) tenant, never Alice's chunks.
    bob_key = client.post("/api-keys", headers=bob.headers, json={"name": "bob"}).json()["key"]
    r = client.post(
        "/search", headers={"X-API-Key": bob_key}, json={"query": "launch code ZULU-7788"}
    )
    assert r.status_code == 200
    assert r.json()["results"] == []
