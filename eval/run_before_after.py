#!/usr/bin/env python
"""AtlasKB before/after benchmark (Trust Layer T9.1).

Runs the T7 dataset (``dataset.json``) against a live backend exactly once,
under whatever T9.0 component-toggle flags the backend process was started
with, and writes a labelled result set. Run this script twice — once against
a backend started with the "before" flags, once with "after" — then pass both
result files to ``compare_before_after.py`` to produce the comparison table.

This intentionally reuses run_eval.py's question-loop logic (duplicated, not
imported, so this script has no import-time dependency on run_eval.py's own
__main__ guard) and adds two metrics run_eval.py doesn't compute:

  * citation_coverage — of an answerable+answered question's answer, what
    fraction of its sentences are covered by at least one citation whose
    claim text overlaps that sentence. Operationalizes "claim-level citation
    granularity" (Phase T2) as a number: 1.0 means every sentence carries its
    own citation, not one blanket citation for the whole answer.
  * permission_leakage — a dedicated check (not part of the question loop):
    a document is granted to one role only; a user WITHOUT that role searches
    for content unique to it, and the check is whether the chunk ID itself
    ever appears in retrieved results — not whether the answer text mentions
    it, since a leak could occur in retrieval even if generation didn't quote
    it. Must be 0 in every configuration; if it isn't, that's reported, not
    hidden.

Usage (from repo root, backend running with the flags for this run):
    uv run --project apps/api python eval/run_before_after.py --label before
    uv run --project apps/api python eval/run_before_after.py --label after
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
DATASET = HERE / "dataset.json"
RESULTS_DIR = HERE / "results"
MODEL = os.environ.get("OPENROUTER_MODEL", "backend-configured")

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]


def citation_coverage(answer: str, citations: list[dict]) -> float | None:
    """Fraction of the answer's sentences matched by at least one citation's
    claim text (case-insensitive substring overlap, either direction)."""
    sentences = [s.strip() for s in _SENTENCE_RE.findall(answer) if s.strip()]
    if not sentences:
        return None
    claims = [(c.get("claim") or "").strip().lower() for c in citations]
    claims = [c for c in claims if c]
    if not claims:
        return 0.0
    covered = 0
    for sentence in sentences:
        s = sentence.lower()
        if any(claim in s or s in claim for claim in claims):
            covered += 1
    return round(covered / len(sentences), 3)


def run_dataset(c: httpx.Client, headers: dict, doc_by_id: dict[str, str]) -> tuple[list[dict], list[float], list[int]]:
    dataset = json.loads(DATASET.read_text())
    questions = dataset["questions"]

    results = []
    latencies: list[float] = []
    tokens_per_query: list[int] = []
    for q in questions:
        t0 = time.perf_counter()
        resp = c.post("/chat", headers=headers, json={"question": q["question"]})
        dt = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()
        latencies.append(dt)
        tokens_per_query.append(data.get("usage", {}).get("total", 0))

        chunk_doc = {ch["chunk_id"]: ch["document_id"] for ch in data["retrieved"]}
        retrieved_docs = {doc_by_id.get(d) for d in chunk_doc.values()}
        cited_docs = {
            doc_by_id.get(chunk_doc.get(cid))
            for cit in data["citations"]
            for cid in cit["chunk_ids"]
        }
        answer_lower = (data["answer"] or "").lower()

        hit = q["expected_doc"] in retrieved_docs if q["expected_doc"] else None
        answered_correctly = (
            any(s.lower() in answer_lower for s in q["expected_substrings"])
            if q["answerable"] and q["expected_substrings"]
            else None
        )
        grounded = (
            (q["expected_doc"] in cited_docs) if (q["answerable"] and data["answerable"]) else None
        )
        refusal_correct = (data["answerable"] is False) if not q["answerable"] else None

        expect_conflict = q.get("expect_conflict")
        conflict_detected = len(data.get("conflicts") or []) > 0
        conflict_correct = (
            (conflict_detected == expect_conflict) if expect_conflict is not None else None
        )

        coverage = (
            citation_coverage(data["answer"], data["citations"])
            if (q["answerable"] and data["answerable"])
            else None
        )

        results.append(
            {
                "question": q["question"],
                "expected_doc": q["expected_doc"],
                "answerable_expected": q["answerable"],
                "answerable_actual": data["answerable"],
                "retrieval_hit": hit,
                "answer_correct": answered_correctly,
                "citation_grounded": grounded,
                "citation_coverage": coverage,
                "refusal_correct": refusal_correct,
                "expect_conflict": expect_conflict,
                "conflict_detected": conflict_detected,
                "conflict_correct": conflict_correct,
                "tokens": data.get("usage", {}).get("total", 0),
                "latency_ms": round(dt, 1),
                "answer": data["answer"],
            }
        )
        print(
            f"  {q['question'][:48]:50s} hit={hit} correct={answered_correctly} "
            f"grounded={grounded} coverage={coverage} refuse={refusal_correct} "
            f"conflict={conflict_correct} {dt:.0f}ms"
        )
    return results, latencies, tokens_per_query


def check_permission_leakage(c: httpx.Client) -> dict:
    """Dedicated ACL check, independent of the T7 dataset: a document is
    restricted to the admin role only; a viewer searches for its unique
    content and we check the chunk ID never appears in retrieved results —
    not just that the answer text omits it."""
    admin_email = f"eval-admin-{uuid.uuid4().hex[:8]}@example.com"
    password = "eval-password-123"
    c.post("/auth/signup", json={"email": admin_email, "password": password}).raise_for_status()
    admin_tokens = c.post("/auth/login", json={"email": admin_email, "password": password}).json()
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    ws = c.post("/workspaces", headers=admin_headers, json={"name": "leak-check"})
    ws.raise_for_status()
    ws_id = ws.json()["id"]
    admin_headers["X-Workspace-Id"] = ws_id

    secret_text = "# Executive Compensation\n\nThe QUEBEC-4471-CONFIDENTIAL figure is $4.2M.\n"
    r = c.post(
        "/documents", headers=admin_headers,
        files={"file": ("exec-comp.md", secret_text.encode(), "text/markdown")},
    )
    r.raise_for_status()
    doc_id = r.json()["id"]
    for _ in range(30):
        d = c.get(f"/documents/{doc_id}", headers=admin_headers).json()
        if d["status"] != "processing":
            break
        time.sleep(1)
    if d["status"] != "ready":
        return {"pass": False, "error": f"setup doc failed to ingest: {d}"}

    # Restrict to admin role only.
    r = c.patch(
        f"/documents/{doc_id}/access", headers=admin_headers,
        json={"grants": [{"grant_type": "role", "role_or_user_id": "admin"}]},
    )
    r.raise_for_status()
    restricted_chunk_ids = {
        layer["chunk_id"]
        for layer in c.get(f"/documents/{doc_id}/chunks", headers=admin_headers).json()["layers"]
    }

    # A real workspace member at viewer role -- via the actual invite/accept
    # HTTP flow (InviteOut returns the token directly, no email delivery
    # needed for a scripted check), not a DB-level shortcut. This is the
    # scenario that actually matters: a legitimate member of the workspace,
    # below the granted role, must never see the restricted chunk.
    viewer_email = f"eval-viewer-{uuid.uuid4().hex[:8]}@example.com"
    inv = c.post(
        f"/workspaces/{ws_id}/invites", headers=admin_headers,
        json={"email": viewer_email, "role": "viewer"},
    )
    inv.raise_for_status()
    token = inv.json()["token"]

    c.post("/auth/signup", json={"email": viewer_email, "password": password}).raise_for_status()
    viewer_tokens = c.post("/auth/login", json={"email": viewer_email, "password": password}).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_tokens['access_token']}"}
    c.post(f"/invites/{token}/accept", headers=viewer_headers).raise_for_status()
    viewer_headers["X-Workspace-Id"] = ws_id

    r = c.post("/search", headers=viewer_headers, json={"query": "QUEBEC-4471-CONFIDENTIAL"})
    r.raise_for_status()
    leaked = [
        h["chunk_id"] for h in r.json().get("results", []) if h["chunk_id"] in restricted_chunk_ids
    ]

    # Also check the outer boundary: a user with NO membership in the
    # workspace at all must be rejected before retrieval ever runs.
    outsider_email = f"eval-outsider-{uuid.uuid4().hex[:8]}@example.com"
    c.post("/auth/signup", json={"email": outsider_email, "password": password}).raise_for_status()
    outsider_tokens = c.post("/auth/login", json={"email": outsider_email, "password": password}).json()
    outsider_headers = {
        "Authorization": f"Bearer {outsider_tokens['access_token']}",
        "X-Workspace-Id": ws_id,
    }
    r2 = c.post("/search", headers=outsider_headers, json={"query": "QUEBEC-4471-CONFIDENTIAL"})
    outsider_rejected = r2.status_code in (403, 404)

    return {
        "pass": not leaked and outsider_rejected,
        "restricted_chunk_ids": sorted(restricted_chunk_ids),
        "viewer_search_status": r.status_code,
        "leaked_chunk_ids": sorted(leaked),
        "outsider_search_status": r2.status_code,
        "outsider_correctly_rejected": outsider_rejected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="e.g. before, after, A, C, D, E")
    parser.add_argument(
        "--out-prefix", default="before_after", help="results/<prefix>_<label>.json"
    )
    args = parser.parse_args()

    with httpx.Client(base_url=BASE, timeout=120) as c:
        email = f"eval-{uuid.uuid4().hex[:10]}@example.com"
        password = "eval-password-123"
        c.post("/auth/signup", json={"email": email, "password": password}).raise_for_status()
        tokens = c.post("/auth/login", json={"email": email, "password": password}).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        ws = c.post("/workspaces", headers=headers, json={"name": f"eval-{args.label}"})
        ws.raise_for_status()
        headers["X-Workspace-Id"] = ws.json()["id"]

        doc_by_id: dict[str, str] = {}
        for path in sorted(CORPUS.glob("*.md")):
            files = {"file": (path.name, path.read_bytes(), "text/markdown")}
            r = c.post("/documents", headers=headers, files=files)
            r.raise_for_status()
            doc_by_id[r.json()["id"]] = path.name
        print(f"[{args.label}] uploaded {len(doc_by_id)} documents; waiting for ingestion…")

        deadline = time.time() + 120
        while time.time() < deadline:
            docs = c.get("/documents", headers=headers).json()
            statuses = {d["status"] for d in docs}
            if statuses == {"ready"}:
                break
            if "failed" in statuses:
                raise SystemExit(f"a document failed to ingest: {docs}")
            time.sleep(2)
        else:
            raise SystemExit("documents did not become ready in time")

        print(f"[{args.label}] running {json.loads(DATASET.read_text())['questions'].__len__()} questions…")
        results, latencies, tokens_per_query = run_dataset(c, headers, doc_by_id)

        print(f"[{args.label}] checking permission leakage…")
        leakage = check_permission_leakage(c)
        print(f"[{args.label}] permission leakage check: {'PASS' if leakage['pass'] else 'FAIL'}")

    def rate(key: str, cond) -> float | None:
        relevant = [r for r in results if cond(r) and r[key] is not None]
        if not relevant:
            return None
        passed = sum(1 for r in relevant if r[key] is True)
        return round(passed / len(relevant), 3)

    def avg(key: str, cond) -> float | None:
        relevant = [r[key] for r in results if cond(r) and r[key] is not None]
        return round(statistics.mean(relevant), 3) if relevant else None

    metrics = {
        "answer_accuracy": rate("answer_correct", lambda r: r["answerable_expected"]),
        "citation_grounding": rate(
            "citation_grounded", lambda r: r["answerable_expected"] and r["answerable_actual"]
        ),
        "citation_coverage": avg(
            "citation_coverage", lambda r: r["answerable_expected"] and r["answerable_actual"]
        ),
        "refusal_accuracy": rate("refusal_correct", lambda r: not r["answerable_expected"]),
        "retrieval_hit_rate": rate("retrieval_hit", lambda r: r["expected_doc"] is not None),
        "conflict_detection_accuracy": rate(
            "conflict_correct", lambda r: r["expect_conflict"] is not None
        ),
        "permission_leakage": 0 if leakage["pass"] else len(leakage["leaked_chunk_ids"]),
        "avg_tokens_per_query": round(statistics.mean(tokens_per_query), 1) if tokens_per_query else 0,
        "latency_p50_ms": round(pctl(latencies, 50), 1),
        "latency_p95_ms": round(pctl(latencies, 95), 1),
    }

    payload = {
        "label": args.label,
        "generated_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "dataset_size": len(json.loads(DATASET.read_text())["questions"]),
        "corpus_size": len(list(CORPUS.glob("*.md"))),
        "metrics": metrics,
        "permission_leakage_detail": leakage,
        "results": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{args.out_prefix}_{args.label}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\n=== [{args.label}] metrics ===")
    print(json.dumps(metrics, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
