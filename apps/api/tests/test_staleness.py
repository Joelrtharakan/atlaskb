"""Document freshness/staleness signal + Dashboard relief endpoint.

Display-only feature: verifies the derived staleness decay, the verify action,
and that the relief map is workspace/ACL-scoped (never leaks a restricted doc).
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.models import Document

SAMPLE_MD = "# Fresh\n\nThe knowledge base is current and verified.\n"


def _upload(client, headers, name="fresh.md"):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(SAMPLE_MD.encode()), "text/markdown")},
    )


def test_staleness_property_decays_with_age():
    """0 when just created, ~0.5 at half the max age, capped at 1.0 when old."""
    now = datetime.now(UTC)
    fresh = Document(created_at=now)
    assert fresh.staleness < 0.001  # ~0 (a few ns of age)

    half = Document(created_at=now - timedelta(days=settings.staleness_max_age_days / 2))
    assert 0.4 < half.staleness < 0.6

    ancient = Document(created_at=now - timedelta(days=settings.staleness_max_age_days * 3))
    assert ancient.staleness == 1.0

    # Verification resets the clock: an old doc verified today reads as fresh.
    verified = Document(
        created_at=now - timedelta(days=settings.staleness_max_age_days * 3),
        last_verified_at=now,
    )
    assert verified.staleness < 0.001


def test_document_out_exposes_staleness(client, auth_headers, ingest_inline):
    _upload(client, auth_headers)
    docs = client.get("/documents", headers=auth_headers).json()
    assert docs
    assert "staleness" in docs[0]
    assert docs[0]["staleness"] < 0.001  # just created
    assert docs[0]["last_verified_at"] is None


def test_verify_sets_last_verified(client, auth_headers, ingest_inline):
    doc_id = _upload(client, auth_headers).json()["id"]
    r = client.post(f"/documents/{doc_id}/verify", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["last_verified_at"] is not None
    assert body["staleness"] < 0.001


def test_relief_endpoint_returns_mass_and_staleness(client, auth_headers, ingest_inline):
    _upload(client, auth_headers)
    r = client.get("/dashboard/relief", headers=auth_headers)
    assert r.status_code == 200
    cells = r.json()["cells"]
    assert cells
    cell = cells[0]
    assert cell["mass"] >= 1  # chunk count drives peak height
    assert "staleness" in cell


def test_relief_is_acl_scoped(client, make_user, grant_membership, ingest_inline):
    """A restricted document must not appear on another member's relief map."""
    admin = make_user()  # owns a workspace
    _upload(client, admin.headers, name="restricted.md")
    doc_id = client.get("/documents", headers=admin.headers).json()[0]["id"]
    # Restrict to admins only.
    client.patch(
        f"/documents/{doc_id}/access",
        headers=admin.headers,
        json={"grants": [{"grant_type": "role", "role_or_user_id": "admin"}]},
    )

    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")
    cells = client.get(
        "/dashboard/relief", headers=viewer.in_ws(admin.workspace_id)
    ).json()["cells"]
    assert all(c["id"] != doc_id for c in cells)
