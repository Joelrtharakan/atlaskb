#!/usr/bin/env python
"""AtlasKB security hardening (Trust Layer Phase 9) — checks that don't fit
the prompt-injection fixture format in `run_prompt_injection.py`.

Every check here inspects real retrieved chunk IDs and authorization
context, not just generated text — a model that merely *says* the right
thing while the wrong chunk was actually retrieved is not a pass.

  * API key workspace confusion — an API key's workspace is fixed at
    creation; does presenting `X-Workspace-Id` for a DIFFERENT workspace
    alongside it let a caller read that other workspace's data?
  * Version leakage — does a historical/version-specific question ever
    return current-version chunks (or vice versa) in its actual retrieved
    set, not just in the answer's wording?

Usage (from repo root, backend running):
    uv run --project apps/api python eval/run_security_hardening.py
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
PASSWORD = "eval-password-123"


def _signup_login(c: httpx.Client, email: str) -> dict:
    c.post("/auth/signup", json={"email": email, "password": PASSWORD}).raise_for_status()
    tokens = c.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _new_workspace(c: httpx.Client, headers: dict, name: str) -> str:
    ws = c.post("/workspaces", headers=headers, json={"name": name})
    ws.raise_for_status()
    return ws.json()["id"]


def _upload_and_wait(c: httpx.Client, headers: dict, filename: str, text: str) -> str:
    r = c.post("/documents", headers=headers, files={"file": (filename, text.encode(), "text/markdown")})
    r.raise_for_status()
    doc_id = r.json()["id"]
    for _ in range(30):
        d = c.get(f"/documents/{doc_id}", headers=headers).json()
        if d["status"] != "processing":
            break
        time.sleep(1)
    if d["status"] != "ready":
        raise RuntimeError(f"document failed to ingest: {d}")
    return doc_id


def check_api_key_workspace_confusion(c: httpx.Client) -> dict:
    """Mint an API key scoped to workspace A (which has a secret document).
    Use that key with X-Workspace-Id pointing at an unrelated workspace B
    (which has its OWN, different secret). If the key's fixed workspace can
    be overridden by the header, B's search results would leak. Checked by
    inspecting actual retrieved chunk IDs, not answer text."""
    a_headers = _signup_login(c, f"eval-keyconf-a-{uuid.uuid4().hex[:8]}@example.com")
    a_ws = _new_workspace(c, a_headers, "keyconf-a")
    a_headers["X-Workspace-Id"] = a_ws
    a_marker = f"ALPHA-{uuid.uuid4().hex[:8].upper()}"
    _upload_and_wait(c, a_headers, "a-secret.md", f"# A Secret\n\nThe code is {a_marker}.\n")

    key_resp = c.post("/api-keys", headers=a_headers, json={"name": "test-key"})
    key_resp.raise_for_status()
    api_key = key_resp.json()["key"]

    b_headers = _signup_login(c, f"eval-keyconf-b-{uuid.uuid4().hex[:8]}@example.com")
    b_ws = _new_workspace(c, b_headers, "keyconf-b")
    b_headers["X-Workspace-Id"] = b_ws
    b_marker = f"BRAVO-{uuid.uuid4().hex[:8].upper()}"
    b_doc_id = _upload_and_wait(c, b_headers, "b-secret.md", f"# B Secret\n\nThe code is {b_marker}.\n")
    b_chunk_ids = {
        layer["chunk_id"] for layer in c.get(f"/documents/{b_doc_id}/chunks", headers=b_headers).json()["layers"]
    }

    # The confused-deputy attempt: A's API key + B's workspace header.
    confused_headers = {"X-API-Key": api_key, "X-Workspace-Id": b_ws}
    r = c.post("/search", headers=confused_headers, json={"query": b_marker, "top_k": 10})
    if r.status_code >= 400:
        return {"pass": True, "detail": f"request rejected outright ({r.status_code}) -- also safe"}
    retrieved_ids = {h["chunk_id"] for h in r.json().get("results", [])}
    leaked = bool(retrieved_ids & b_chunk_ids)
    return {
        "pass": not leaked,
        "status_code": r.status_code,
        "leaked_b_chunks": leaked,
        "retrieved_count": len(retrieved_ids),
    }


def check_version_leakage(c: httpx.Client) -> dict:
    """A current-version question must never retrieve superseded-version
    chunks, and a version-specific historical question must never retrieve
    the current version's chunks -- checked against actual chunk_id/
    version_id pairs in the response, not the answer's wording."""
    headers = _signup_login(c, f"eval-versionleak-{uuid.uuid4().hex[:8]}@example.com")
    ws = _new_workspace(c, headers, "version-leakage")
    headers["X-Workspace-Id"] = ws
    doc_id = _upload_and_wait(c, headers, "policy.md", "# Retention Policy\n\nUNIQUEV1TOKEN: data kept 90 days.\n")
    v1_chunk_ids = {
        layer["chunk_id"] for layer in c.get(f"/documents/{doc_id}/chunks", headers=headers).json()["layers"]
    }

    c.post(
        f"/documents/{doc_id}/reupload", headers=headers,
        files={"file": ("policy.md", b"# Retention Policy\n\nUNIQUEV2TOKEN: data kept 180 days.\n", "text/markdown")},
    ).raise_for_status()
    time.sleep(1)
    v2_chunk_ids = set()
    for v in c.get(f"/documents/{doc_id}/versions", headers=headers).json()["versions"]:
        if v["is_current_version"]:
            v2_chunk_ids = {
                layer["chunk_id"]
                for layer in c.get(
                    f"/documents/{doc_id}/versions/{v['id']}/chunks", headers=headers
                ).json()["layers"]
            }

    r_current = c.post("/chat", headers=headers, json={"question": "What is the retention policy?"})
    r_current.raise_for_status()
    current_retrieved = {ch["chunk_id"] for ch in r_current.json()["retrieved"]}
    current_leaked_v1 = bool(current_retrieved & v1_chunk_ids)

    r_hist = c.post("/chat", headers=headers, json={"question": "What did version 1 say about retention?"})
    r_hist.raise_for_status()
    hist_data = r_hist.json()
    hist_retrieved = {ch["chunk_id"] for ch in hist_data["retrieved"]}
    hist_leaked_v2 = bool(hist_retrieved & v2_chunk_ids)

    return {
        "pass": not current_leaked_v1 and not hist_leaked_v2,
        "current_question_leaked_old_version": current_leaked_v1,
        "historical_question_leaked_current_version": hist_leaked_v2,
        "historical_temporal_intent": (hist_data.get("temporal") or {}).get("intent"),
    }


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=120) as c:
        checks = {
            "api_key_workspace_confusion": check_api_key_workspace_confusion(c),
            "version_leakage": check_version_leakage(c),
        }

    for name, result in checks.items():
        status = "PASS" if result["pass"] else "FAIL"
        print(f"[{status}] {name}: {json.dumps({k: v for k, v in result.items() if k != 'pass'})}")

    passed_n = sum(1 for r in checks.values() if r["pass"])
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(checks),
        "passed": passed_n,
        "failed": len(checks) - passed_n,
        "checks": checks,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "security_hardening.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\n=== {passed_n}/{len(checks)} passed ===")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
