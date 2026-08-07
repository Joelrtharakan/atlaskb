#!/usr/bin/env python
"""AtlasKB load test for /search and /chat.

Measures p50/p95/p99 latency and throughput under concurrency, for both cold
(cache-miss) and warm (cache-hit) paths, and records the cache hit rate.

/search is retrieval-only (fast, local). /chat is dominated by the external LLM,
so it is exercised at low volume. Run the API with RATE_LIMIT_ENABLED=false so
the limiter doesn't distort latency (see README).

Usage (from repo root, backend running):
    uv run python eval/load_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
OUT = Path(__file__).resolve().parent / "results" / "load-latest.json"
CORPUS = Path(__file__).resolve().parent / "corpus"


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]


def summarize(name: str, latencies: list[float], cached_flags: list[bool], wall: float) -> dict:
    n = len(latencies)
    return {
        "name": name,
        "requests": n,
        "wall_seconds": round(wall, 2),
        "throughput_rps": round(n / wall, 1) if wall else 0.0,
        "p50_ms": round(pctl(latencies, 50), 1),
        "p95_ms": round(pctl(latencies, 95), 1),
        "p99_ms": round(pctl(latencies, 99), 1),
        "mean_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
        "cache_hit_rate": round(sum(cached_flags) / n, 3) if n and cached_flags else None,
    }


async def run_phase(
    client: httpx.AsyncClient,
    headers: dict,
    name: str,
    path: str,
    payloads: list[dict],
    concurrency: int,
) -> dict:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    cached_flags: list[bool] = []
    errors = 0

    async def one(body: dict) -> None:
        nonlocal errors
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.post(path, headers=headers, json=body)
                dt = (time.perf_counter() - t0) * 1000
                if r.status_code == 200:
                    latencies.append(dt)
                    cached_flags.append(bool(r.json().get("cached")))
                else:
                    errors += 1
            except Exception:  # noqa: BLE001 - count transport errors, keep going
                errors += 1

    t0 = time.perf_counter()
    await asyncio.gather(*(one(b) for b in payloads))
    wall = time.perf_counter() - t0
    summary = summarize(name, latencies, cached_flags, wall)
    summary["errors"] = errors
    print(json.dumps(summary))
    return summary


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as c:
        email = f"load-{uuid.uuid4().hex[:10]}@example.com"
        pw = "load-password-123"
        (await c.post("/auth/signup", json={"email": email, "password": pw})).raise_for_status()
        tokens = (await c.post("/auth/login", json={"email": email, "password": pw})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        files = {"file": ("zubrowka.md", (CORPUS / "zubrowka.md").read_bytes(), "text/markdown")}
        (await c.post("/documents", headers=headers, files=files)).raise_for_status()
        deadline = time.time() + 90
        while time.time() < deadline:
            docs = (await c.get("/documents", headers=headers)).json()
            if docs and all(d["status"] == "ready" for d in docs):
                break
            await asyncio.sleep(2)

        # Warm up the in-process embedding model (lazy-loaded on first use) so its
        # one-time load doesn't pollute the measured tail.
        for _ in range(3):
            await c.post("/search", headers=headers, json={"query": "warmup"})

        phases = []
        # /search cold: unique queries → every request is a cache miss (full
        # dense+sparse retrieval). Embedding is CPU-bound/in-process, so throughput
        # is bounded by a single uvicorn worker.
        phases.append(
            await run_phase(
                c, headers, "search_cold", "/search",
                [{"query": f"zubrowka capital currency variant {i}"} for i in range(200)],
                concurrency=10,
            )
        )
        # /search warm: prime once, then a repeated query → all cache hits.
        await c.post("/search", headers=headers, json={"query": "what is the capital of zubrowka"})
        phases.append(
            await run_phase(
                c, headers, "search_warm", "/search",
                [{"query": "what is the capital of zubrowka"} for _ in range(200)],
                concurrency=20,
            )
        )
        # /chat cold: low volume (LLM-bound, free tier).
        phases.append(
            await run_phase(
                c, headers, "chat_cold", "/chat",
                [{"question": f"What is the capital of Zubrowka? (variant {i})"} for i in range(6)],
                concurrency=2,
            )
        )
        # /chat warm: prime once, then repeated question → cache hits, no model cost.
        await c.post("/chat", headers=headers, json={"question": "What currency does Zubrowka use?"})
        phases.append(
            await run_phase(
                c, headers, "chat_warm", "/chat",
                [{"question": "What currency does Zubrowka use?"} for _ in range(20)],
                concurrency=5,
            )
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": BASE,
        "phases": phases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
