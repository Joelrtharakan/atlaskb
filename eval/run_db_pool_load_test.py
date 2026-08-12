#!/usr/bin/env python
"""AtlasKB isolated database/connection-pool load test (Trust Layer T11.2).

Hammers /search with unique queries — guaranteed cache misses, so every
request is a real DB hit — at a concurrency deliberately set ABOVE the API
process's own connection pool ceiling (db_pool_size + db_max_overflow, see
app/config.py), to prove the pool sustains real concurrent load without
connection errors or excessive queuing before any other T11 work (horizontal
scaling, realistic mixed-workload testing) gets layered on top and makes a
pool problem here harder to tell apart from an application-code one.

Run the API with RATE_LIMIT_ENABLED=false, same convention as load_test.py —
otherwise the per-user rate limiter (60 req/min by default), not the DB pool,
is what actually caps throughput at this concurrency, and the result would
misattribute a rate-limit ceiling to a database one.

Usage (from repo root, backend running with RATE_LIMIT_ENABLED=false):
    uv run --project apps/api python eval/run_db_pool_load_test.py
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

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
CORPUS = Path(__file__).resolve().parent / "corpus" / "zubrowka.md"
OUT = Path(__file__).resolve().parent / "results" / "db_pool_load_test.json"

# Deliberately above the default db_pool_size(10) + db_max_overflow(20) = 30,
# so a real pool-exhaustion problem would actually surface here.
CONCURRENCY = 40
REQUESTS = 400


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        email = f"dbload-{uuid.uuid4().hex[:10]}@example.com"
        pw = "load-password-123"
        (await c.post("/auth/signup", json={"email": email, "password": pw})).raise_for_status()
        tokens = (await c.post("/auth/login", json={"email": email, "password": pw})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        ws = (await c.post("/workspaces", headers=headers, json={"name": "db-pool-load-test"})).json()
        headers["X-Workspace-Id"] = ws["id"]

        files = {"file": ("zubrowka.md", CORPUS.read_bytes(), "text/markdown")}
        (await c.post("/documents", headers=headers, files=files)).raise_for_status()
        deadline = time.time() + 90
        while time.time() < deadline:
            docs = (await c.get("/documents", headers=headers)).json()
            if docs and all(d["status"] == "ready" for d in docs):
                break
            await asyncio.sleep(2)

        sem = asyncio.Semaphore(CONCURRENCY)
        latencies: list[float] = []
        errors = 0
        error_samples: list[tuple] = []

        async def one(i: int) -> None:
            nonlocal errors
            async with sem:
                t0 = time.perf_counter()
                try:
                    r = await c.post(
                        "/search",
                        headers=headers,
                        # A unique query per request -- every hit is a real
                        # dense+sparse DB query, never a cache hit.
                        json={"query": f"zubrowka fact variant unique {i} {uuid.uuid4().hex[:8]}"},
                    )
                    dt = (time.perf_counter() - t0) * 1000
                    if r.status_code == 200:
                        latencies.append(dt)
                    else:
                        errors += 1
                        if len(error_samples) < 5:
                            error_samples.append((r.status_code, r.text[:200]))
                except Exception as exc:  # noqa: BLE001 - count transport errors, keep going
                    errors += 1
                    if len(error_samples) < 5:
                        error_samples.append(("exception", str(exc)[:200]))

        t0 = time.perf_counter()
        await asyncio.gather(*(one(i) for i in range(REQUESTS)))
        wall = time.perf_counter() - t0

        result = {
            "requests": REQUESTS,
            "concurrency": CONCURRENCY,
            "wall_seconds": round(wall, 2),
            "throughput_rps": round(REQUESTS / wall, 1) if wall else 0.0,
            "p50_ms": round(pctl(latencies, 50), 1),
            "p95_ms": round(pctl(latencies, 95), 1),
            "p99_ms": round(pctl(latencies, 99), 1),
            "mean_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
            "errors": errors,
            "error_rate": round(errors / REQUESTS, 4),
            "error_samples": error_samples,
        }
        print(json.dumps(result, indent=2))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
