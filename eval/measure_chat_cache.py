#!/usr/bin/env python
"""Measure the /chat cache-HIT latency path (no LLM call).

A cache hit skips the agent/LLM entirely and serves the stored answer, so it can
be measured without spending model quota by pre-seeding the semantic cache (which
is exactly what a warm cache is). Updates eval/results/load-latest.json with a
``chat_warm`` phase.

Usage (from repo root, backend running):
    uv run python eval/measure_chat_cache.py
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
import uuid
from pathlib import Path

import httpx
from app.cache import cache_key, cache_set
from app.config import settings

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
OUT = Path(__file__).resolve().parent / "results" / "load-latest.json"
Q = "Cache-hit measurement: what is the capital of Zubrowka?"


def pctl(v: list[float], p: float) -> float:
    if not v:
        return 0.0
    s = sorted(v)
    return s[max(0, min(len(s) - 1, round((p / 100) * len(s) + 0.5) - 1))]


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        email = f"cache-{uuid.uuid4().hex[:10]}@example.com"
        pw = "cache-password-123"
        r = await c.post("/auth/signup", json={"email": email, "password": pw})
        r.raise_for_status()
        user_id = r.json()["id"]
        tokens = (await c.post("/auth/login", json={"email": email, "password": pw})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        tenant_id = (await c.get("/workspaces", headers=headers)).json()[0]["id"]

        # Seed the cache exactly as the endpoint would key it.
        key = cache_key(
            namespace="chat",
            tenant_id=tenant_id,
            user_id=user_id,
            model=f"{settings.openrouter_model}:k8",
            query=Q,
        )
        cache_set(
            key,
            {
                "answerable": True,
                "answer": "The capital of Zubrowka is Lutz.",
                "citations": [],
                "retrieved": [],
                "iterations": 1,
                "queries": [Q],
            },
        )

        primed = await c.post("/chat", headers=headers, json={"question": Q})
        assert primed.json()["cached"] is True, "expected a cache hit after seeding"

        sem = asyncio.Semaphore(10)
        lat: list[float] = []
        hits = 0

        async def one() -> None:
            nonlocal hits
            async with sem:
                t0 = time.perf_counter()
                resp = await c.post("/chat", headers=headers, json={"question": Q})
                lat.append((time.perf_counter() - t0) * 1000)
                if resp.json().get("cached"):
                    hits += 1

        n = 100
        t0 = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(n)))
        wall = time.perf_counter() - t0

        phase = {
            "name": "chat_warm",
            "requests": n,
            "wall_seconds": round(wall, 2),
            "throughput_rps": round(n / wall, 1),
            "p50_ms": round(pctl(lat, 50), 1),
            "p95_ms": round(pctl(lat, 95), 1),
            "p99_ms": round(pctl(lat, 99), 1),
            "mean_ms": round(statistics.mean(lat), 1),
            "cache_hit_rate": round(hits / n, 3),
            "errors": 0,
            "note": "cache-seeded (no LLM call); measures the cache-hit request path",
        }
        print(json.dumps(phase, indent=2))

    if OUT.exists():
        data = json.loads(OUT.read_text())
        data["phases"] = [p for p in data.get("phases", []) if p.get("name") != "chat_warm"]
        data["phases"].append(phase)
        OUT.write_text(json.dumps(data, indent=2))
        print(f"\nupdated {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
