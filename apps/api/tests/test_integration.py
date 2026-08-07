"""Integration tests for auth, documents, search, and chat against a real
Postgres+pgvector test database. Retrieval runs for real; the LLM is stubbed.
"""

from __future__ import annotations

import io

SAMPLE_MD = """# Solar System

The Sun is the star at the center of the Solar System.

## Planets

Mars is the fourth planet from the Sun and is often called the Red Planet.
Jupiter is the largest planet in the Solar System.
"""


def _upload_md(client, headers, name="solar.md", body=SAMPLE_MD):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(body.encode()), "text/markdown")},
    )


# --- Auth ---
def test_signup_login_refresh_and_protection(client):
    r = client.post("/auth/signup", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 201

    assert (
        client.post("/auth/signup", json={"email": "a@b.com", "password": "password123"}).status_code
        == 409
    )
    assert (
        client.post("/auth/login", json={"email": "a@b.com", "password": "wrong"}).status_code == 401
    )

    tokens = client.post(
        "/auth/login", json={"email": "a@b.com", "password": "password123"}
    ).json()
    assert tokens["access_token"] and tokens["refresh_token"]

    # Protected endpoint requires a token.
    assert client.get("/documents").status_code in (401, 403)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/documents", headers=headers).status_code == 200

    refreshed = client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()
    h2 = {"Authorization": f"Bearer {refreshed['access_token']}"}
    assert client.get("/documents", headers=h2).status_code == 200


def test_access_token_cannot_be_used_as_refresh(client, auth_headers):
    access = auth_headers["Authorization"].split()[1]
    assert client.post("/auth/refresh", json={"refresh_token": access}).status_code == 401


# --- Documents ---
def test_upload_lists_and_reaches_ready(client, auth_headers, ingest_inline):
    r = _upload_md(client, auth_headers)
    assert r.status_code == 201
    doc = r.json()
    assert doc["status"] == "processing"

    detail = client.get(f"/documents/{doc['id']}", headers=auth_headers).json()
    assert detail["status"] == "ready"
    assert detail["chunk_count"] >= 1

    listing = client.get("/documents", headers=auth_headers).json()
    assert any(d["id"] == doc["id"] for d in listing)


def test_unsupported_file_type_rejected(client, auth_headers):
    r = client.post(
        "/documents",
        headers=auth_headers,
        files={"file": ("data.bin", io.BytesIO(b"\x00\x01"), "application/octet-stream")},
    )
    assert r.status_code == 415


# --- Search ---
def test_hybrid_search_returns_ranked_chunks(client, auth_headers, ingest_inline):
    _upload_md(client, auth_headers)
    r = client.post("/search", headers=auth_headers, json={"query": "Red Planet Mars", "top_k": 5})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    scores = [x["score"] for x in results]
    assert scores == sorted(scores, reverse=True)
    assert any("Mars" in x["text"] for x in results)


# --- Chat (agent + citations) ---
def test_chat_returns_cited_answer(client, auth_headers, ingest_inline, stub_llm):
    _upload_md(client, auth_headers)
    r = client.post("/chat", headers=auth_headers, json={"question": "What is the Red Planet?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answerable"] is True
    assert data["citations"]
    assert data["conversation_id"]
    assert data["cached"] is False
    cited = data["citations"][0]["chunk_ids"][0]
    assert cited in {c["chunk_id"] for c in data["retrieved"]}


def test_chat_cannot_answer_when_no_documents(client, auth_headers):
    # No documents -> retrieval empty -> agent answers "cannot" without any
    # network call (generate/assess short-circuit on empty context).
    r = client.post("/chat", headers=auth_headers, json={"question": "Anything?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answerable"] is False
    assert "cannot answer" in data["answer"].lower()


def test_chat_persists_conversation(client, auth_headers, ingest_inline, stub_llm):
    _upload_md(client, auth_headers)
    convo_id = client.post(
        "/chat", headers=auth_headers, json={"question": "What is the Red Planet?"}
    ).json()["conversation_id"]

    detail = client.get(f"/conversations/{convo_id}", headers=auth_headers).json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
