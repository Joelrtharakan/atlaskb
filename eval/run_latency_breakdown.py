#!/usr/bin/env python
"""AtlasKB per-stage latency breakdown (Trust Layer T9.5).

Runs real questions against a live backend started with EXPOSE_TIMING=true
and collects the per-stage timing (`ChatResponse.timing`, see app/timing.py)
that /chat now reports on every non-cached turn. Produces p50/p95 per stage,
not an estimate.

Usage (from repo root, backend running with EXPOSE_TIMING=true):
    uv run --project apps/api python eval/run_latency_breakdown.py --label ollama [--limit N]
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
DATASET = HERE / "dataset.json"
RESULTS_DIR = HERE / "results"
PASSWORD = "eval-password-123"


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="e.g. ollama, openrouter")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of questions run")
    args = parser.parse_args()

    questions = json.loads(DATASET.read_text())["questions"]
    # Only answerable questions actually exercise generation/conflict-check
    # meaningfully; refusal questions short-circuit before most stages run.
    questions = [q for q in questions if q["answerable"]]
    if args.limit:
        questions = questions[: args.limit]

    with httpx.Client(base_url=BASE, timeout=180) as c:
        email = f"eval-lat-{uuid.uuid4().hex[:8]}@example.com"
        c.post("/auth/signup", json={"email": email, "password": PASSWORD}).raise_for_status()
        tokens = c.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        ws = c.post("/workspaces", headers=headers, json={"name": f"latency-{args.label}"})
        ws.raise_for_status()
        headers["X-Workspace-Id"] = ws.json()["id"]

        for path in sorted(CORPUS.glob("*.md")):
            files = {"file": (path.name, path.read_bytes(), "text/markdown")}
            c.post("/documents", headers=headers, files=files).raise_for_status()
        print(f"[{args.label}] uploaded corpus; waiting for ingestion…")
        deadline = time.time() + 120
        while time.time() < deadline:
            docs = c.get("/documents", headers=headers).json()
            if all(d["status"] == "ready" for d in docs):
                break
            time.sleep(2)
        else:
            raise SystemExit("documents did not become ready in time")

        per_stage: dict[str, list[float]] = {}
        rows = []
        for q in questions:
            print(f"[{args.label}] asking: {q['question'][:60]!r}")
            r = c.post("/chat", headers=headers, json={"question": q["question"]})
            r.raise_for_status()
            data = r.json()
            timing = data.get("timing") or {}
            if not timing:
                print("  (no timing on this response — was EXPOSE_TIMING set? skipping)")
                continue
            for stage, ms in timing.items():
                per_stage.setdefault(stage, []).append(ms)
            rows.append({"question": q["question"], "timing": timing})
            print(f"  {timing}")

    stage_stats = {
        stage: {
            "p50_ms": round(pctl(values, 50), 1),
            "p95_ms": round(pctl(values, 95), 1),
            "mean_ms": round(sum(values) / len(values), 1),
            "n": len(values),
        }
        for stage, values in per_stage.items()
    }

    payload = {
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "questions_run": len(rows),
        "stage_stats": stage_stats,
        "rows": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"latency_breakdown_{args.label}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\n=== [{args.label}] stage stats ===")
    print(json.dumps(stage_stats, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
