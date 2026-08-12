"""'Why this answer?' evidence (Trust Layer T5): per-cited-source retrieval
scores + document freshness + version, surfaced on the chat response."""

from __future__ import annotations

import io

MD = """# Falcon Spec

The Falcon Arm v2 has a reach of 900mm and a payload of 12kg.
"""


def _upload(client, headers):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": ("falcon.md", io.BytesIO(MD.encode()), "text/markdown")},
    )


def test_chat_evidence_matches_citations(client, auth_headers, ingest_inline, stub_llm):
    doc_id = _upload(client, auth_headers).json()["id"]
    r = client.post("/chat", headers=auth_headers, json={"question": "What is the reach?"})
    assert r.status_code == 200
    body = r.json()
    assert body["citations"]
    cited_ids = {cid for c in body["citations"] for cid in c["chunk_ids"]}

    assert body["evidence"]
    evidence_ids = {e["chunk_id"] for e in body["evidence"]}
    assert evidence_ids == cited_ids

    e = body["evidence"][0]
    assert e["document_id"] == doc_id
    assert e["filename"] == "falcon.md"
    assert e["version_number"] == 1
    assert e["is_current_version"] is True
    assert 0.0 <= e["staleness"] <= 1.0
    assert e["last_verified_at"] is None  # never verified yet


def test_verify_document_reflected_in_evidence(client, auth_headers, ingest_inline, stub_llm):
    doc_id = _upload(client, auth_headers).json()["id"]
    v = client.post(f"/documents/{doc_id}/verify", headers=auth_headers)
    assert v.status_code == 200

    r = client.post("/chat", headers=auth_headers, json={"question": "What is the payload?"})
    body = r.json()
    assert body["evidence"]
    assert body["evidence"][0]["last_verified_at"] is not None
    assert body["evidence"][0]["staleness"] < 0.001


def test_no_evidence_when_unanswerable(client, auth_headers, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "anything at all"})
    assert r.status_code == 200
    body = r.json()
    assert not body["answerable"]
    assert body["evidence"] == []
