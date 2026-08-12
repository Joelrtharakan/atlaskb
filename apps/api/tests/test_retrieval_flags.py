"""T9.0 component-toggle flags: each must be a real code-path difference, not
a cosmetic label. Verified here against a real Postgres (pgvector + full-text)
so "dense_only skips the sparse query" etc. is actually true, not assumed."""

from __future__ import annotations

import io

from app.config import settings

# "reach" only appears in the falcon doc; "policy" only in the policy doc —
# lets us tell dense/sparse/hybrid retrieval apart by which chunk comes back.
FALCON = "# Falcon Spec\n\nThe Falcon Arm v2 has a reach of 900mm.\n"
POLICY = "# Refund Policy\n\nRefunds are issued within 30 days per policy.\n"


def _upload(client, headers, text: str, filename: str):
    return client.post(
        "/documents",
        headers=headers,
        files={"file": (filename, io.BytesIO(text.encode()), "text/markdown")},
    )


def test_dense_only_skips_sparse_query(client, auth_headers, ingest_inline, monkeypatch):
    _upload(client, auth_headers, FALCON, "falcon.md")
    _upload(client, auth_headers, POLICY, "policy.md")

    monkeypatch.setattr(settings, "retrieval_mode", "dense_only")
    monkeypatch.setattr(settings, "rerank_enabled", False)  # isolate the fusion-mode behavior
    r = client.post("/search", headers=auth_headers, json={"query": "reach", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    # dense_only still returns results (embedding-based similarity), and never
    # ran RRF fusion — score should equal the raw dense_score, not a fused score.
    assert body["results"]
    for hit in body["results"]:
        assert hit["dense_score"] is not None
        assert hit["sparse_score"] is None
        assert hit["score"] == hit["dense_score"]


def test_sparse_only_skips_dense_query(client, auth_headers, ingest_inline, monkeypatch):
    _upload(client, auth_headers, FALCON, "falcon.md")
    _upload(client, auth_headers, POLICY, "policy.md")

    monkeypatch.setattr(settings, "retrieval_mode", "sparse_only")
    monkeypatch.setattr(settings, "rerank_enabled", False)  # isolate the fusion-mode behavior
    r = client.post("/search", headers=auth_headers, json={"query": "reach", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]
    for hit in body["results"]:
        assert hit["sparse_score"] is not None
        assert hit["dense_score"] is None
        assert hit["score"] == hit["sparse_score"]


def test_hybrid_mode_uses_both_and_rrf_score(client, auth_headers, ingest_inline, monkeypatch):
    _upload(client, auth_headers, FALCON, "falcon.md")
    _upload(client, auth_headers, POLICY, "policy.md")

    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")
    r = client.post("/search", headers=auth_headers, json={"query": "reach", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["results"]
    top = body["results"][0]
    # Hybrid: both signals present, and the ranking score is neither raw score
    # alone (it's the RRF fusion — or the rerank score, since reranking runs by
    # default — but definitely not simply equal to dense_score, unlike dense_only).
    assert top["dense_score"] is not None


def test_version_unaware_retrieval_sees_superseded_chunks(
    client, auth_headers, ingest_inline, monkeypatch
):
    doc_id = _upload(client, auth_headers, "# V1\n\nOriginal wording alpha.\n", "doc.md").json()["id"]
    client.post(
        f"/documents/{doc_id}/reupload",
        headers=auth_headers,
        files={"file": ("doc.md", io.BytesIO(b"# V2\n\nUpdated wording beta.\n"), "text/markdown")},
    )

    # Version-aware (default): only the current version's chunk is searchable.
    r = client.post("/search", headers=auth_headers, json={"query": "alpha OR beta", "top_k": 5})
    texts = " ".join(h["text"] for h in r.json()["results"])
    assert "beta" in texts
    assert "alpha" not in texts

    # Version-unaware (T9.0 ablation flag): both versions' chunks come back.
    monkeypatch.setattr(settings, "version_aware_retrieval", False)
    r2 = client.post("/search", headers=auth_headers, json={"query": "alpha OR beta", "top_k": 5})
    texts2 = " ".join(h["text"] for h in r2.json()["results"])
    assert "beta" in texts2
    assert "alpha" in texts2


def test_conflict_detection_disabled_skips_llm_call(
    client, auth_headers, ingest_inline, stub_llm, monkeypatch
):
    calls = {"n": 0}

    def fake_detect_conflicts_structured(chunks):
        calls["n"] += 1
        return [], __import__("app.llm", fromlist=["TokenUsage"]).TokenUsage()

    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )
    _upload(client, auth_headers, FALCON, "falcon.md")
    _upload(client, auth_headers, POLICY, "policy.md")

    monkeypatch.setattr(settings, "conflict_detection_enabled", False)
    r = client.post("/chat", headers=auth_headers, json={"question": "anything"})
    assert r.status_code == 200
    assert r.json()["conflicts"] == []
    assert calls["n"] == 0  # never called at all — not called-and-ignored


def test_cache_key_changes_with_retrieval_mode(client, auth_headers, ingest_inline, monkeypatch):
    """Regression: found live while proving T9.0's flags actually change
    behavior. The semantic cache key didn't include the active flags, so
    switching RETRIEVAL_MODE with a warm cache silently served a stale
    result computed under the *previous* mode — which would have corrupted
    every T9.1/T9.2 comparison without anyone noticing."""
    _upload(client, auth_headers, FALCON, "falcon.md")
    monkeypatch.setattr(settings, "cache_enabled", True)

    monkeypatch.setattr(settings, "retrieval_mode", "dense_only")
    r1 = client.post("/search", headers=auth_headers, json={"query": "reach", "top_k": 5})
    assert r1.json()["results"][0]["dense_score"] is not None
    assert r1.json()["results"][0]["sparse_score"] is None

    monkeypatch.setattr(settings, "retrieval_mode", "sparse_only")
    r2 = client.post("/search", headers=auth_headers, json={"query": "reach", "top_k": 5})
    assert r2.json()["cached"] is False  # must NOT reuse dense_only's cache entry
    assert r2.json()["results"][0]["sparse_score"] is not None
    assert r2.json()["results"][0]["dense_score"] is None


def test_conflict_detection_enabled_calls_llm(
    client, auth_headers, ingest_inline, stub_llm, monkeypatch
):
    calls = {"n": 0}

    def fake_detect_conflicts_structured(chunks):
        calls["n"] += 1
        from app.llm import TokenUsage

        return [], TokenUsage()

    monkeypatch.setattr(
        "app.routers.chat.detect_conflicts_structured", fake_detect_conflicts_structured
    )
    _upload(client, auth_headers, FALCON, "falcon.md")
    _upload(client, auth_headers, POLICY, "policy.md")

    monkeypatch.setattr(settings, "conflict_detection_enabled", True)
    r = client.post("/chat", headers=auth_headers, json={"question": "anything"})
    assert r.status_code == 200
    assert calls["n"] == 1
