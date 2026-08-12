#!/usr/bin/env python
"""Real latency measurement per trust mode (Trust Layer Phase 4 DoD item:
"Latency is measured for each trust mode"). Uploads the same two
conflicting documents, asks the same question under FAST/BALANCED/MAX_TRUST,
and records total wall-clock + per-stage breakdown (requires the API to be
running with EXPOSE_TIMING=true).

Usage (from repo root, backend running with EXPOSE_TIMING=true):
    uv run --project apps/api python eval/run_trust_mode_latency.py
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
PASSWORD = "eval-password-123"

PTO_HR = "# PTO Policy\n\nAll full-time employees accrue paid time off (PTO) at a rate of 1.5 days per month, up to an annual cap of 18 days.\n"
PTO_ENG = "# Engineering Time Off\n\nEngineering is an unlimited-PTO team: there is no accrual and no annual cap.\n"

MODES = ["FAST", "BALANCED", "MAX_TRUST"]
REPEATS = 4  # per mode, excluding the first (cache-cold) request


def _signup_login(c: httpx.Client, email: str) -> dict:
    c.post("/auth/signup", json={"email": email, "password": PASSWORD}).raise_for_status()
    tokens = c.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _upload_and_wait(c: httpx.Client, headers: dict, filename: str, text: str) -> None:
    r = c.post("/documents", headers=headers, files={"file": (filename, text.encode(), "text/markdown")})
    r.raise_for_status()
    doc_id = r.json()["id"]
    for _ in range(30):
        d = c.get(f"/documents/{doc_id}", headers=headers).json()
        if d["status"] != "processing":
            break
        time.sleep(1)


def main() -> None:
    email = f"trust-mode-latency-{int(time.time())}@example.com"
    with httpx.Client(base_url=BASE, timeout=180) as c:
        headers = _signup_login(c, email)
        ws = c.post("/workspaces", headers=headers, json={"name": "trust-mode-latency"})
        ws.raise_for_status()
        headers["X-Workspace-Id"] = ws.json()["id"]

        _upload_and_wait(c, headers, "hr.md", PTO_HR)
        _upload_and_wait(c, headers, "eng.md", PTO_ENG)

        results: dict[str, dict] = {}
        for mode in MODES:
            print(f"=== {mode} ===")
            totals: list[float] = []
            stage_totals: dict[str, list[float]] = {}
            for i in range(REPEATS):
                # A distinct question per call defeats the semantic cache so
                # every request does real work — repeated latency, not one
                # cold call followed by cache hits.
                question = f"How much PTO do employees get? (run {i}, mode {mode})"
                t0 = time.perf_counter()
                r = c.post(
                    "/chat", headers=headers,
                    json={"question": question, "trust_mode": mode},
                )
                r.raise_for_status()
                wall_ms = (time.perf_counter() - t0) * 1000
                totals.append(wall_ms)
                body = r.json()
                timing = body.get("timing") or {}
                for stage, ms in timing.items():
                    stage_totals.setdefault(stage, []).append(ms)
                print(
                    f"  run {i}: {wall_ms:.0f} ms wall, conflicts={len(body['conflicts'])}, "
                    f"evidence={len(body['evidence'])}"
                )

            def _avg(xs: list[float]) -> float:
                return round(sum(xs) / len(xs), 1) if xs else 0.0

            results[mode] = {
                "wall_ms_avg": _avg(totals),
                "wall_ms_all": [round(t, 1) for t in totals],
                "stage_avg_ms": {stage: _avg(vals) for stage, vals in stage_totals.items()},
            }

    out = {
        "generated_at": datetime.now(UTC).isoformat(),
        "modes": results,
    }
    print()
    print(json.dumps(out, indent=2))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "trust_mode_latency.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
