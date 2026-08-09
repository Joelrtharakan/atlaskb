"""Document chunks endpoint that feeds the Core Sample view."""

from __future__ import annotations

import io

MD = """# Falcon Spec

The Falcon Arm v2 has a reach of 900mm and a payload of 12kg.

## Power

It draws 48V DC. The controller runs the northwind/tap/nw-cli stack.
"""


def _upload(client, headers):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": ("falcon.md", io.BytesIO(MD.encode()), "text/markdown")},
    )


def test_chunks_endpoint_returns_strata(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers).json()["id"]
    r = client.get(f"/documents/{doc_id}/chunks", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["document_id"] == doc_id
    assert body["layers"]
    for layer in body["layers"]:
        assert layer["length"] > 0
        assert 0.0 <= layer["confidence"] <= 1.0
        assert 0.0 <= layer["staleness"] <= 1.0
        assert layer["preview"]


def test_chunks_missing_document_404(client, auth_headers):
    r = client.get("/documents/00000000-0000-0000-0000-000000000000/chunks", headers=auth_headers)
    assert r.status_code == 404
