#!/usr/bin/env python
"""AtlasKB expanded evaluation (Trust Layer Phase 3).

Two parts, because a static labeled-question list can only express so much:

1. **Categorized QA** (`dataset_expanded.json`) — retrieval (direct lookup,
   semantic, keyword, multi-hop, cross-document), answer quality, citations,
   trust (conflicts). Same grading mechanism as `run_eval.py` (kept
   unchanged, still the fast single-command smoke check), extended with
   per-category breakdown and an optional `require_all_substrings` flag for
   completeness checks.
2. **Dedicated live checks** for everything a static QA list can't express:
   ACL bypass (reuses `run_before_after.check_permission_leakage` rather
   than reimplementing it), cross-tenant retrieval leakage, cached-answer
   leakage across workspaces, staleness actually reaching the model
   (real DB backdating, same technique `docs/DEMO_SCRIPT.md`'s manual setup
   uses), and a real version-comparison round-trip through `/chat`.

**Honest scope note**: this does NOT reach the phase spec's 300-question
target. See `eval/EXPANDED_EVAL_README.md` for why, and what would be needed
to actually get there. Every question and check here is real — answered
against a live backend, not fabricated — but the count is what it is.

Usage (from repo root, backend running):
    uv run --project apps/api python eval/run_expanded_eval.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_before_after import check_permission_leakage  # noqa: E402

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
DATASET = HERE / "dataset_expanded.json"
RESULTS_DIR = HERE / "results"
OUT = RESULTS_DIR / "expanded_eval.json"
BASELINE = RESULTS_DIR / "expanded_eval_baseline.json"
PASSWORD = "eval-password-123"

# Metrics a regression on is worth failing the run for. Deliberately narrow —
# this is a smoke check for "did something break", not a general quality bar.
REGRESSION_METRICS = ["answer_accuracy", "retrieval_hit_rate", "refusal_accuracy"]
REGRESSION_THRESHOLD = 0.10  # a drop of more than 10 points on any metric above


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]


def _signup_login(c: httpx.Client, email: str) -> dict:
    c.post("/auth/signup", json={"email": email, "password": PASSWORD}).raise_for_status()
    tokens = c.post("/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _new_workspace(c: httpx.Client, headers: dict, name: str) -> str:
    ws = c.post("/workspaces", headers=headers, json={"name": name})
    ws.raise_for_status()
    return ws.json()["id"]


def _upload_and_wait(c: httpx.Client, headers: dict, filename: str, text: str) -> str:
    r = c.post(
        "/documents", headers=headers,
        files={"file": (filename, text.encode(), "text/markdown")},
    )
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


# --- Part 1: categorized QA ---


def run_categorized_dataset(c: httpx.Client, headers: dict, doc_by_id: dict[str, str]) -> list[dict]:
    dataset = json.loads(DATASET.read_text())
    results = []
    for q in dataset["questions"]:
        t0 = time.perf_counter()
        resp = c.post("/chat", headers=headers, json={"question": q["question"]})
        dt = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        data = resp.json()

        chunk_doc = {ch["chunk_id"]: ch["document_id"] for ch in data["retrieved"]}
        retrieved_docs = {doc_by_id.get(d) for d in chunk_doc.values()}
        cited_docs = {
            doc_by_id.get(chunk_doc.get(cid))
            for cit in data["citations"]
            for cid in cit["chunk_ids"]
        }
        answer_lower = (data["answer"] or "").lower()

        hit = q["expected_doc"] in retrieved_docs if q["expected_doc"] else None
        substrings = q.get("expected_substrings") or []
        if q["answerable"] and substrings:
            answered_correctly = (
                all(s.lower() in answer_lower for s in substrings)
                if q.get("require_all_substrings")
                else any(s.lower() in answer_lower for s in substrings)
            )
        else:
            answered_correctly = None
        grounded = (
            (q["expected_doc"] in cited_docs) if (q["answerable"] and data["answerable"]) else None
        )
        refusal_correct = (data["answerable"] is False) if not q["answerable"] else None
        expect_conflict = q.get("expect_conflict")
        conflict_detected = len(data.get("conflicts") or []) > 0
        conflict_correct = (
            (conflict_detected == expect_conflict) if expect_conflict is not None else None
        )

        row = {
            "question": q["question"],
            "category": q.get("category", "uncategorized"),
            "subcategory": q.get("subcategory", ""),
            "expected_doc": q["expected_doc"],
            "answerable_expected": q["answerable"],
            "answerable_actual": data["answerable"],
            "retrieval_hit": hit,
            "answer_correct": answered_correctly,
            "citation_grounded": grounded,
            "refusal_correct": refusal_correct,
            "conflict_correct": conflict_correct,
            "latency_ms": round(dt, 1),
            "answer": data["answer"],
        }
        results.append(row)
        print(
            f"  [{row['category']}/{row['subcategory']}] {q['question'][:44]:46s} "
            f"hit={hit} correct={answered_correctly} grounded={grounded} refuse={refusal_correct}"
        )
    return results


# --- Part 2: dedicated live checks ---


def check_cross_tenant_retrieval_leakage(c: httpx.Client) -> dict:
    """Workspace A has a document with a unique marker; a completely separate
    workspace B (different owner, never invited to A) asks about it. Checks
    the marker's chunk ID never appears in B's retrieved results — not just
    that B's answer text omits it."""
    a_headers = _signup_login(c, f"eval-tenant-a-{uuid.uuid4().hex[:8]}@example.com")
    a_ws = _new_workspace(c, a_headers, "tenant-a")
    a_headers["X-Workspace-Id"] = a_ws
    marker = f"ZULU-{uuid.uuid4().hex[:8].upper()}"
    doc_id = _upload_and_wait(c, a_headers, "secret.md", f"# Secret\n\nThe code is {marker}.\n")
    a_chunk_ids = {
        layer["chunk_id"] for layer in c.get(f"/documents/{doc_id}/chunks", headers=a_headers).json()["layers"]
    }

    b_headers = _signup_login(c, f"eval-tenant-b-{uuid.uuid4().hex[:8]}@example.com")
    b_ws = _new_workspace(c, b_headers, "tenant-b")
    b_headers["X-Workspace-Id"] = b_ws
    r = c.post("/chat", headers=b_headers, json={"question": f"What is the code {marker}?"})
    r.raise_for_status()
    data = r.json()
    retrieved_ids = {ch["chunk_id"] for ch in data["retrieved"]}
    leaked = bool(retrieved_ids & a_chunk_ids) or marker in (data.get("answer") or "")
    return {"pass": not leaked, "marker": marker, "leaked": leaked}


def check_cached_answer_does_not_cross_workspaces(c: httpx.Client) -> dict:
    """Two separate workspaces each upload a document with the SAME filename
    but workspace-unique content, then ask the identical literal question.
    The cache key includes workspace_id, so each must get its own answer —
    not the other's cached one."""
    a_headers = _signup_login(c, f"eval-cache-a-{uuid.uuid4().hex[:8]}@example.com")
    a_ws = _new_workspace(c, a_headers, "cache-a")
    a_headers["X-Workspace-Id"] = a_ws
    _upload_and_wait(c, a_headers, "answer.md", "# Answer\n\nThe magic number is 4471.\n")

    b_headers = _signup_login(c, f"eval-cache-b-{uuid.uuid4().hex[:8]}@example.com")
    b_ws = _new_workspace(c, b_headers, "cache-b")
    b_headers["X-Workspace-Id"] = b_ws
    _upload_and_wait(c, b_headers, "answer.md", "# Answer\n\nThe magic number is 9203.\n")

    question = "What is the magic number?"
    ra = c.post("/chat", headers=a_headers, json={"question": question}).json()
    rb = c.post("/chat", headers=b_headers, json={"question": question}).json()
    a_ok = "4471" in (ra.get("answer") or "")
    b_ok = "9203" in (rb.get("answer") or "") and "4471" not in (rb.get("answer") or "")
    return {"pass": a_ok and b_ok, "a_answer": ra.get("answer"), "b_answer": rb.get("answer")}


def check_staleness_reaches_model(c: httpx.Client, admin_db_url: str | None) -> dict:
    """Real DB backdating (same technique as docs/DEMO_SCRIPT.md's manual
    demo setup) so a document is genuinely stale, then checks both the
    Evidence.staleness signal and Phase 5's Trust Summary reflect it."""
    if not admin_db_url:
        return {"pass": None, "skipped": "no DATABASE_URL available for backdating"}
    import psycopg

    # psycopg wants a plain postgresql:// DSN; SQLAlchemy's own
    # postgresql+psycopg:// dialect prefix isn't a valid libpq scheme.
    dsn = admin_db_url.replace("postgresql+psycopg://", "postgresql://")

    headers = _signup_login(c, f"eval-stale-{uuid.uuid4().hex[:8]}@example.com")
    ws = _new_workspace(c, headers, "staleness-check")
    headers["X-Workspace-Id"] = ws
    doc_id = _upload_and_wait(
        c, headers, "old-policy.md", "# Old Policy\n\nThe retention period is 90 days.\n"
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(
            "UPDATE documents SET created_at = now() - interval '200 days' WHERE id = %s",
            (doc_id,),
        )
    r = c.post("/chat", headers=headers, json={"question": "What is the retention period?"})
    r.raise_for_status()
    data = r.json()
    evidence = data.get("evidence") or []
    stale_evidence = any(e["staleness"] > 0.5 for e in evidence)
    freshness = (data.get("trust_summary") or {}).get("source_freshness")
    return {
        "pass": stale_evidence and freshness == "Low",
        "stale_evidence": stale_evidence,
        "trust_summary_freshness": freshness,
    }


def check_version_comparison_live(c: httpx.Client) -> dict:
    """Real reupload -> real version history -> a real 'what changed?'
    question through /chat, checking the Phase 2 temporal path actually
    engages and returns a structured diff citing both versions."""
    headers = _signup_login(c, f"eval-version-{uuid.uuid4().hex[:8]}@example.com")
    ws = _new_workspace(c, headers, "version-check")
    headers["X-Workspace-Id"] = ws
    doc_id = _upload_and_wait(
        c, headers, "retention.md", "# Retention Policy\n\nData is retained for 90 days.\n"
    )
    r = c.post(
        f"/documents/{doc_id}/reupload", headers=headers,
        files={"file": ("retention.md", b"# Retention Policy\n\nData is retained for 180 days.\n", "text/markdown")},
    )
    r.raise_for_status()
    time.sleep(1)

    r = c.post("/chat", headers=headers, json={"question": "What changed in the retention policy?"})
    r.raise_for_status()
    data = r.json()
    temporal = data.get("temporal") or {}
    diff = temporal.get("diff") or []
    has_conflicting_or_changed = any(e["kind"] in ("CHANGED", "CONFLICTING") for e in diff)
    return {
        "pass": temporal.get("intent") == "CHANGE_SUMMARY" and has_conflicting_or_changed,
        "temporal_intent": temporal.get("intent"),
        "diff_kinds": [e["kind"] for e in diff],
    }


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=180) as c:
        email = f"eval-expanded-{uuid.uuid4().hex[:10]}@example.com"
        headers = _signup_login(c, email)
        ws_id = _new_workspace(c, headers, "expanded-eval")
        headers["X-Workspace-Id"] = ws_id

        doc_by_id: dict[str, str] = {}
        for path in sorted(CORPUS.glob("*.md")):
            files = {"file": (path.name, path.read_bytes(), "text/markdown")}
            r = c.post("/documents", headers=headers, files=files)
            r.raise_for_status()
            doc_by_id[r.json()["id"]] = path.name
        print(f"uploaded {len(doc_by_id)} documents; waiting for ingestion…")
        deadline = time.time() + 180
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

        print("\n=== categorized QA ===")
        qa_results = run_categorized_dataset(c, headers, doc_by_id)

        print("\n=== dedicated live checks ===")
        db_url = os.environ.get("DATABASE_URL")
        checks = {
            "acl_bypass": check_permission_leakage(c),
            "cross_tenant_retrieval_leakage": check_cross_tenant_retrieval_leakage(c),
            "cached_answer_workspace_isolation": check_cached_answer_does_not_cross_workspaces(c),
            "staleness_reaches_model": check_staleness_reaches_model(c, db_url),
            "version_comparison_live": check_version_comparison_live(c),
        }
        for name, result in checks.items():
            status = "SKIP" if result.get("pass") is None else ("PASS" if result["pass"] else "FAIL")
            print(f"  [{status}] {name}")

    def rate(key: str, cond) -> float | None:
        relevant = [r for r in qa_results if cond(r) and r[key] is not None]
        if not relevant:
            return None
        return round(sum(1 for r in relevant if r[key] is True) / len(relevant), 3)

    metrics = {
        "answer_accuracy": rate("answer_correct", lambda r: r["answerable_expected"]),
        "citation_grounding": rate(
            "citation_grounded", lambda r: r["answerable_expected"] and r["answerable_actual"]
        ),
        "refusal_accuracy": rate("refusal_correct", lambda r: not r["answerable_expected"]),
        "retrieval_hit_rate": rate("retrieval_hit", lambda r: r["expected_doc"] is not None),
        "conflict_detection_accuracy": rate("conflict_correct", lambda r: r.get("conflict_correct") is not None),
    }

    by_category: dict[str, dict] = {}
    for r in qa_results:
        cat = r["category"]
        entry = by_category.setdefault(cat, {"total": 0, "hit": 0, "correct": 0, "hit_n": 0, "correct_n": 0})
        entry["total"] += 1
        if r["retrieval_hit"] is not None:
            entry["hit_n"] += 1
            entry["hit"] += int(r["retrieval_hit"])
        if r["answer_correct"] is not None:
            entry["correct_n"] += 1
            entry["correct"] += int(r["answer_correct"])
    for cat, e in by_category.items():
        e["retrieval_hit_rate"] = round(e["hit"] / e["hit_n"], 3) if e["hit_n"] else None
        e["answer_accuracy"] = round(e["correct"] / e["correct_n"], 3) if e["correct_n"] else None

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_size": len(qa_results),
        "corpus_size": len(doc_by_id),
        "metrics": metrics,
        "by_category": by_category,
        "live_checks": checks,
        "results": qa_results,
    }

    print("\n=== metrics ===")
    print(json.dumps(metrics, indent=2))
    print("\n=== by category ===")
    print(json.dumps(by_category, indent=2))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {OUT}")

    # --- Regression detection against a saved baseline ---
    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text())["metrics"]
        regressed = []
        for m in REGRESSION_METRICS:
            old, new = baseline.get(m), metrics.get(m)
            if old is not None and new is not None and (old - new) > REGRESSION_THRESHOLD:
                regressed.append((m, old, new))
        if regressed:
            print("\n=== REGRESSION DETECTED ===")
            for m, old, new in regressed:
                print(f"  {m}: {old} -> {new} (dropped more than {REGRESSION_THRESHOLD})")
            sys.exit(1)
        print(f"\nNo regression vs baseline ({BASELINE.name}) on {REGRESSION_METRICS}.")
    else:
        BASELINE.write_text(json.dumps({"metrics": metrics}, indent=2))
        print(f"\nNo baseline existed — wrote this run as the new baseline ({BASELINE.name}).")


if __name__ == "__main__":
    main()
