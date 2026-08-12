"""Document versioning & lineage (Trust Layer T1): re-upload creates a new
version, retrieval only ever sees the current one, old chunks stay queryable."""

from __future__ import annotations

import io

V1 = """# Refund Policy

Refunds are issued within 30 days of purchase.
"""

V2 = """# Refund Policy

Refunds are issued within 14 days of purchase.
"""


def _upload(client, headers, text: str, filename: str = "policy.md"):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
    )


def _reupload(client, headers, doc_id: str, text: str, filename: str = "policy.md"):
    return client.post(
        f"/documents/{doc_id}/reupload",
        headers=headers,
        files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
    )


def test_upload_creates_version_one(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    r = client.get(f"/documents/{doc_id}/versions", headers=auth_headers)
    assert r.status_code == 200
    versions = r.json()["versions"]
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["is_current_version"] is True
    assert versions[0]["chunk_count"] > 0


def test_reupload_creates_new_current_version(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    r = _reupload(client, auth_headers, doc_id, V2)
    assert r.status_code == 200, r.text

    versions = client.get(f"/documents/{doc_id}/versions", headers=auth_headers).json()["versions"]
    assert len(versions) == 2
    by_number = {v["version_number"]: v for v in versions}
    assert by_number[1]["is_current_version"] is False
    assert by_number[2]["is_current_version"] is True


def test_reupload_identical_content_is_noop(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    r = _reupload(client, auth_headers, doc_id, V1)
    assert r.status_code == 200, r.text

    versions = client.get(f"/documents/{doc_id}/versions", headers=auth_headers).json()["versions"]
    assert len(versions) == 1


def test_retrieval_only_sees_current_version(client, auth_headers, ingest_inline, stub_llm):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    _reupload(client, auth_headers, doc_id, V2)

    r = client.post("/search", headers=auth_headers, json={"query": "refund days", "top_k": 8})
    assert r.status_code == 200
    texts = " ".join(hit["text"] for hit in r.json()["results"])
    assert "14 days" in texts
    assert "30 days" not in texts


def test_old_version_chunks_still_readable(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    _reupload(client, auth_headers, doc_id, V2)

    versions = client.get(f"/documents/{doc_id}/versions", headers=auth_headers).json()["versions"]
    old_version_id = next(v["id"] for v in versions if v["version_number"] == 1)

    r = client.get(f"/documents/{doc_id}/versions/{old_version_id}/chunks", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["layers"]
    assert any("30 days" in layer["preview"] for layer in body["layers"])


def test_current_version_chunks_endpoint_excludes_superseded(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    _reupload(client, auth_headers, doc_id, V2)

    r = client.get(f"/documents/{doc_id}/chunks", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert any("14 days" in layer["preview"] for layer in body["layers"])
    assert not any("30 days" in layer["preview"] for layer in body["layers"])


def test_citations_carry_version_id(client, auth_headers, ingest_inline, stub_llm):
    doc_id = _upload(client, auth_headers, V1).json()["id"]
    r = client.post("/chat", headers=auth_headers, json={"question": "How many days for a refund?"})
    assert r.status_code == 200
    body = r.json()
    assert body["retrieved"]
    assert all(chunk["version_id"] for chunk in body["retrieved"])


def test_retry_recovers_ready_document_with_no_current_version_chunks(
    client, auth_headers, ingest_inline, db
):
    """Regression: a document can end up 'ready' with its chunks pointing at no
    current version (e.g. ingested by code that predates version tagging, or any
    future version-tagging inconsistency). This must never be a dead end — retry
    should be allowed and should re-tag the chunks against a fresh version."""
    from app.models import Chunk

    doc_id = _upload(client, auth_headers, V1).json()["id"]
    detail = client.get(f"/documents/{doc_id}", headers=auth_headers).json()
    assert detail["status"] == "ready"
    assert detail["chunk_count"] == 1

    # Simulate the failure mode directly: chunks with no version_id at all.
    db.query(Chunk).filter(Chunk.document_id == doc_id).update({"version_id": None})
    db.commit()

    broken = client.get(f"/documents/{doc_id}", headers=auth_headers).json()
    assert broken["status"] == "ready"
    assert broken["chunk_count"] == 0  # invisible to retrieval despite "ready"

    r = client.post(f"/documents/{doc_id}/retry", headers=auth_headers)
    assert r.status_code == 200, r.text

    healed = client.get(f"/documents/{doc_id}", headers=auth_headers).json()
    assert healed["status"] == "ready"
    assert healed["chunk_count"] == 1


def test_reupload_requires_manage_permission(client, make_user, grant_membership, ingest_inline):
    owner = make_user()
    doc_id = _upload(client, owner.headers, V1).json()["id"]

    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, owner.workspace_id, "viewer")

    r = _reupload(client, viewer.in_ws(owner.workspace_id), doc_id, V2)
    assert r.status_code == 403
