#!/usr/bin/env python
"""AtlasKB load test for /search and /chat.

Measures p50/p95/p99 latency and throughput under concurrency, for both cold
(cache-miss) and warm (cache-hit) paths, and records the cache hit rate.

/search is retrieval-only (fast, local). /chat is dominated by the external LLM,
so it is exercised at low volume. Run the API with RATE_LIMIT_ENABLED=false so
the limiter doesn't distort latency (see README).

Trust Layer T11.4: pass --mixed to instead run a realistic mixed workload --
most simulated users doing search/cached-chat activity with real think-time
between requests (not N simultaneous fresh requests fired at once, which
isn't how real usage looks), a small fraction doing fresh uncached /chat
that hits the T11.1 LLM concurrency limiter, at increasing concurrent-user
counts until response times or error rates genuinely degrade. Reports the
real breaking point and its bottleneck, in the same honest format as every
other measured number in this project -- never an unqualified "supports N
users" claim. See README's Scalability section for whether this ran against
a single instance or a horizontally-scaled one; T11.4 itself doesn't assume
either, it reports what topology it was actually run against.

Usage (from repo root, backend running):
    uv run python eval/load_test.py            # original cold/warm phases
    uv run python eval/load_test.py --mixed     # T11.4 realistic mixed workload
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import statistics
import sys
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


async def _virtual_user(
    client: httpx.AsyncClient,
    headers: dict,
    seed: int,
    stop_at: float,
    chat_fraction: float,
    warm_query: str,
    warm_question: str,
    events: list[dict],
) -> None:
    """One simulated active user: repeatedly picks an action (weighted
    toward cached search/chat, a small fraction fresh uncached /chat),
    waits real think-time between requests, until ``stop_at``. Never fires
    requests back-to-back with no pause -- that's not how a person using
    the app behaves, and it's the whole reason this differs from
    run_phase()'s all-at-once semaphore-gated bursts above."""
    rng = random.Random(seed)
    while time.perf_counter() < stop_at:
        if rng.random() < chat_fraction:
            action, path, body = (
                "chat_fresh", "/chat",
                {"question": f"{warm_question} (fresh variant {rng.randint(0, 10_000_000)})"},
            )
        elif rng.random() < 0.5:
            action, path, body = "search_cached", "/search", {"query": warm_query}
        else:
            action, path, body = "chat_cached", "/chat", {"question": warm_question}

        t0 = time.perf_counter()
        try:
            r = await client.post(path, headers=headers, json=body, timeout=60)
            dt = (time.perf_counter() - t0) * 1000
            events.append({"action": action, "status": r.status_code, "latency_ms": dt})
        except Exception as exc:  # noqa: BLE001 - count transport errors, keep going
            events.append({"action": action, "status": "error", "latency_ms": None, "error": str(exc)[:120]})

        # Real think-time, not a fixed pace -- 1-4s between a user's actions.
        await asyncio.sleep(rng.uniform(1.0, 4.0))


def _summarize_mixed(concurrent_users: int, duration_s: float, events: list[dict]) -> dict:
    by_action: dict[str, list[dict]] = {}
    for e in events:
        by_action.setdefault(e["action"], []).append(e)

    def action_summary(rows: list[dict]) -> dict:
        ok = [r for r in rows if r["status"] == 200]
        lat = [r["latency_ms"] for r in ok]
        errored = [r for r in rows if r["status"] != 200]
        rate_limited = sum(1 for r in rows if r["status"] == 429)
        return {
            "requests": len(rows),
            "ok": len(ok),
            "errors": len(errored),
            "rate_limited_429": rate_limited,
            "error_rate": round(len(errored) / len(rows), 4) if rows else 0.0,
            "p50_ms": round(pctl(lat, 50), 1),
            "p95_ms": round(pctl(lat, 95), 1),
            "p99_ms": round(pctl(lat, 99), 1),
        }

    cached_rows = by_action.get("search_cached", []) + by_action.get("chat_cached", [])
    return {
        "concurrent_users": concurrent_users,
        "duration_s": duration_s,
        "total_requests": len(events),
        "throughput_rps": round(len(events) / duration_s, 1) if duration_s else 0.0,
        "cached_traffic": action_summary(cached_rows),
        "fresh_chat": action_summary(by_action.get("chat_fresh", [])),
    }


async def run_mixed_workload_sweep(
    client: httpx.AsyncClient,
    headers: dict,
    warm_query: str,
    warm_question: str,
    levels: list[int],
    duration_s: float = 20.0,
    chat_fraction: float = 0.05,
    # Degradation thresholds for the CACHED/search-heavy majority traffic --
    # the fresh-chat fraction is expected to queue/429 well before this
    # (bounded by LLM_CONCURRENCY_LIMIT, a provider/hardware ceiling, not an
    # application-layer one), so it is reported separately and never used to
    # decide where the "real" breaking point is.
    p95_degradation_ms: float = 3000.0,
    error_rate_degradation: float = 0.05,
) -> list[dict]:
    results = []
    for concurrent_users in levels:
        stop_at = time.perf_counter() + duration_s
        events: list[dict] = []
        users = [
            _virtual_user(client, headers, seed, stop_at, chat_fraction, warm_query, warm_question, events)
            for seed in range(concurrent_users)
        ]
        t0 = time.perf_counter()
        await asyncio.gather(*users)
        actual_duration = time.perf_counter() - t0

        summary = _summarize_mixed(concurrent_users, actual_duration, events)
        print(json.dumps(summary, indent=2))
        results.append(summary)

        cached = summary["cached_traffic"]
        degraded = cached["p95_ms"] > p95_degradation_ms or cached["error_rate"] > error_rate_degradation
        if degraded:
            print(
                f"\n>>> Degradation at {concurrent_users} concurrent users: "
                f"cached-traffic p95={cached['p95_ms']}ms (threshold {p95_degradation_ms}ms), "
                f"error_rate={cached['error_rate']} (threshold {error_rate_degradation}). Stopping sweep."
            )
            break
    return results


async def run_mixed(base: str) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=60) as c:
        email = f"mixed-{uuid.uuid4().hex[:10]}@example.com"
        pw = "load-password-123"
        (await c.post("/auth/signup", json={"email": email, "password": pw})).raise_for_status()
        tokens = (await c.post("/auth/login", json={"email": email, "password": pw})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        ws = (await c.post("/workspaces", headers=headers, json={"name": "mixed-load-test"})).json()
        headers["X-Workspace-Id"] = ws["id"]

        files = {"file": ("zubrowka.md", (CORPUS / "zubrowka.md").read_bytes(), "text/markdown")}
        (await c.post("/documents", headers=headers, files=files)).raise_for_status()
        deadline = time.time() + 90
        while time.time() < deadline:
            docs = (await c.get("/documents", headers=headers)).json()
            if docs and all(d["status"] == "ready" for d in docs):
                break
            await asyncio.sleep(2)

        warm_query = "what is the capital of zubrowka"
        warm_question = "What currency does Zubrowka use?"
        # Prime both caches once before the sweep so "cached" traffic really
        # is cache hits from request one, not a cold miss counted as cached.
        await c.post("/search", headers=headers, json={"query": warm_query})
        await c.post("/chat", headers=headers, json={"question": warm_question})

        results = await run_mixed_workload_sweep(
            c, headers, warm_query, warm_question, levels=[50, 200, 500, 1000],
        )

    out = Path(__file__).resolve().parent / "results" / "mixed_workload_load_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"generated_at": datetime.now(UTC).isoformat(), "base_url": base, "levels": results}, indent=2))
    print(f"\nwrote {out}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as c:
        email = f"load-{uuid.uuid4().hex[:10]}@example.com"
        pw = "load-password-123"
        (await c.post("/auth/signup", json={"email": email, "password": pw})).raise_for_status()
        tokens = (await c.post("/auth/login", json={"email": email, "password": pw})).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        # A user has no workspace until one is created (see app/routers/auth.py) --
        # every workspace-scoped call below needs X-Workspace-Id, found missing
        # (this script 400'd on the very next call) while building T11.2.
        ws = (await c.post("/workspaces", headers=headers, json={"name": "load-test"})).json()
        headers["X-Workspace-Id"] = ws["id"]

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
    if "--mixed" in sys.argv:
        asyncio.run(run_mixed(BASE))
    else:
        asyncio.run(main())
