"""Cache write-invalidation (Trust Layer Phase 8).

Before this phase, the cache was purely TTL-based — a document reupload, an
ACL change, or a role change could leave a stale cached answer being served
for up to `cache_ttl_seconds` after the underlying state changed. These
tests prove that no longer happens: an invalidating event makes an
identical follow-up question a cache MISS, not a stale hit.

Cross-workspace/cross-user isolation itself (the cache key already includes
workspace_id and user_id) is covered by `test_cache.py`; this file is
specifically about invalidation on write.
"""

from __future__ import annotations

import io

import pytest
from app.config import settings
from app.llm import Assessment, GroundedAnswer


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setattr(settings, "cache_enabled", True)


@pytest.fixture
def counting_llm(monkeypatch):
    calls = {"generate": 0}

    def fake_assess(question, chunks):
        return Assessment(sufficient=True)

    def fake_generate(question, chunks):
        calls["generate"] += 1
        if not chunks:
            return GroundedAnswer(False, "cannot", [])
        return GroundedAnswer(
            True, f"answer {calls['generate']} about {chunks[0].text[:20]}",
            [{"claim": "c", "chunk_ids": [chunks[0].chunk_id]}],
        )

    monkeypatch.setattr("app.llm.assess_context", fake_assess)
    monkeypatch.setattr("app.llm.generate_answer", fake_generate)
    return calls


def _upload(client, headers, body=b"# Doc\n\nMars is the Red Planet.\n", filename="d.md"):
    return client.post(
        "/documents", headers=headers, files={"file": (filename, io.BytesIO(body), "text/markdown")}
    )


def test_reupload_invalidates_cached_answer(client, make_user, ingest_inline, cache_on, counting_llm):
    user = make_user()
    doc = _upload(client, user.headers).json()

    r1 = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r1.json()["cached"] is False
    r2 = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r2.json()["cached"] is True
    assert counting_llm["generate"] == 1

    # New content, same document -> a new version -> must invalidate.
    client.post(
        f"/documents/{doc['id']}/reupload", headers=user.headers,
        files={"file": ("d.md", io.BytesIO(b"# Doc\n\nMars has two moons.\n"), "text/markdown")},
    )

    r3 = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r3.json()["cached"] is False, "reupload must invalidate the prior cached answer"
    assert counting_llm["generate"] == 2


def test_new_upload_invalidates_a_stale_cached_refusal(
    client, make_user, ingest_inline, cache_on, counting_llm
):
    """A cached "cannot answer" is just as stale as a cached wrong answer
    once a document that actually answers the question shows up."""
    user = make_user()

    r1 = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r1.json()["cached"] is False
    assert r1.json()["answerable"] is False
    r2 = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r2.json()["cached"] is True
    assert counting_llm["generate"] == 1  # fake_generate never even ran (no chunks) -- assess/generate skipped

    _upload(client, user.headers)  # now something exists that could answer it

    r3 = client.post("/chat", headers=user.headers, json={"question": "What is Mars?"})
    assert r3.json()["cached"] is False, "a new document must invalidate a stale cached refusal"


def test_acl_grant_change_invalidates_cache(client, make_user, grant_membership, ingest_inline, cache_on, counting_llm):
    admin = make_user()
    viewer = make_user(create_workspace=False)
    grant_membership(viewer.user_id, admin.workspace_id, "viewer")
    doc = _upload(client, admin.headers).json()
    viewer_headers = viewer.in_ws(admin.workspace_id)

    r1 = client.post("/chat", headers=viewer_headers, json={"question": "What is Mars?"})
    assert r1.json()["cached"] is False
    r2 = client.post("/chat", headers=viewer_headers, json={"question": "What is Mars?"})
    assert r2.json()["cached"] is True

    # Restrict the document to admins only -- the viewer's cached answer,
    # computed when they could see it, must not keep being served.
    client.patch(
        f"/documents/{doc['id']}/access", headers=admin.headers,
        json={"grants": [{"grant_type": "role", "role_or_user_id": "admin"}]},
    )

    r3 = client.post("/chat", headers=viewer_headers, json={"question": "What is Mars?"})
    assert r3.json()["cached"] is False, "an ACL change must invalidate previously-cached answers"
    assert r3.json()["answerable"] is False  # and the new (correct) answer reflects the restriction


def test_role_downgrade_invalidates_cache(client, make_user, grant_membership, ingest_inline, cache_on, counting_llm):
    admin = make_user()
    member = make_user(create_workspace=False)
    grant_membership(member.user_id, admin.workspace_id, "editor")
    _upload(client, admin.headers)
    member_headers = member.in_ws(admin.workspace_id)

    r1 = client.post("/chat", headers=member_headers, json={"question": "What is Mars?"})
    assert r1.json()["cached"] is False
    r2 = client.post("/chat", headers=member_headers, json={"question": "What is Mars?"})
    assert r2.json()["cached"] is True

    client.patch(
        f"/workspaces/{admin.workspace_id}/members/{member.user_id}",
        headers=admin.headers, json={"role": "viewer"},
    )

    r3 = client.post("/chat", headers=member_headers, json={"question": "What is Mars?"})
    assert r3.json()["cached"] is False, "a role change must invalidate that workspace's cached answers"


def test_epoch_bump_is_scoped_to_its_own_workspace(
    client, make_user, ingest_inline, cache_on, counting_llm
):
    """Invalidating workspace A must not touch workspace B's cache."""
    alice = make_user()
    bob = make_user()
    _upload(client, alice.headers)
    _upload(client, bob.headers)

    client.post("/chat", headers=alice.headers, json={"question": "What is Mars?"})
    client.post("/chat", headers=bob.headers, json={"question": "What is Mars?"})
    assert counting_llm["generate"] == 2

    # A new upload into Alice's workspace bumps only Alice's epoch.
    _upload(client, alice.headers, filename="second.md")

    a_again = client.post("/chat", headers=alice.headers, json={"question": "What is Mars?"})
    b_again = client.post("/chat", headers=bob.headers, json={"question": "What is Mars?"})
    assert a_again.json()["cached"] is False  # Alice's workspace changed -> miss
    assert b_again.json()["cached"] is True  # Bob's workspace is untouched -> still a hit
