"""Per-stage timing breakdown (T9.5) — off by default, populated only when
settings.expose_timing is on."""

from __future__ import annotations

from app.config import settings


def test_timing_absent_by_default(client, auth_headers, stub_llm):
    r = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    assert r.status_code == 200
    assert r.json()["timing"] is None


def test_timing_present_when_enabled(client, auth_headers, stub_llm, monkeypatch):
    monkeypatch.setattr(settings, "expose_timing", True)
    r = client.post("/chat", headers=auth_headers, json={"question": "hello?"})
    assert r.status_code == 200
    timing = r.json()["timing"]
    assert timing is not None
    assert "total" in timing
    assert "auth" in timing
    assert timing["total"] >= 0


def test_timing_absent_on_cache_hit(client, auth_headers, stub_llm, monkeypatch):
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "expose_timing", True)
    q = {"question": "cached timing check?"}
    client.post("/chat", headers=auth_headers, json=q)
    r2 = client.post("/chat", headers=auth_headers, json=q)
    assert r2.json()["cached"] is True
    assert r2.json()["timing"] is None
