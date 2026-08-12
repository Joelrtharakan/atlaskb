#!/usr/bin/env python
"""AtlasKB adversarial / failure-case evaluation (Trust Layer T9.3).

Unlike run_eval.py / run_before_after.py, this is pass/fail on specific
failure modes, not a graded quality score. A permission leak or a
silently-resolved conflict is an automatic fail regardless of how good the
rest of the answer reads. Run against a backend started with the full/default
Trust Layer config (all T9.0 flags on) — this evaluates real production
behavior, not an ablated one.

Usage (from repo root, backend running):
    uv run --project apps/api python eval/run_adversarial.py
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from run_before_after import check_permission_leakage

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


def test_no_answer(c: httpx.Client) -> dict:
    """1. A question entirely outside the corpus must be explicitly refused,
    not answered with a fabricated fact."""
    headers = _signup_login(c, f"eval-adv1-{uuid.uuid4().hex[:8]}@example.com")
    headers["X-Workspace-Id"] = _new_workspace(c, headers, "adv-no-answer")
    _upload_and_wait(c, headers, "spec.md", "# Falcon Spec\n\nThe Falcon Arm v2 has a reach of 900mm.\n")

    r = c.post("/chat", headers=headers, json={"question": "What is the capital of France?"})
    r.raise_for_status()
    data = r.json()
    passed = data["answerable"] is False
    return {
        "name": "no_answer",
        "pass": passed,
        "detail": {"answerable": data["answerable"], "answer": data["answer"]},
    }


def test_conflicting_sources(c: httpx.Client) -> dict:
    """2. A question hitting known-conflicting documents must produce a
    detected, surfaced conflict — not a silently-picked single answer."""
    headers = _signup_login(c, f"eval-adv2-{uuid.uuid4().hex[:8]}@example.com")
    headers["X-Workspace-Id"] = _new_workspace(c, headers, "adv-conflict")
    _upload_and_wait(
        c, headers, "hr.md",
        "# PTO Policy (HR Handbook)\n\nPTO accrues at 1.5 days per month, capped at 18 days per year.\n",
    )
    _upload_and_wait(
        c, headers, "eng.md",
        "# Engineering Handbook\n\nEngineering is unlimited PTO with no accrual and no annual cap.\n",
    )

    r = c.post("/chat", headers=headers, json={"question": "How much PTO do employees get?"})
    r.raise_for_status()
    data = r.json()
    passed = len(data.get("conflicts") or []) > 0
    return {
        "name": "conflicting_sources",
        "pass": passed,
        "detail": {"conflicts": data.get("conflicts"), "answer": data["answer"]},
    }


def test_stale_source(c: httpx.Client) -> dict:
    """3. A question only answerable from an old/unverified document must
    surface a staleness caveat in the answer text itself, not state the fact
    with unqualified confidence. The document is backdated directly in the
    database (documented, not hidden) since waiting 90+ real days isn't a
    viable test setup."""
    headers = _signup_login(c, f"eval-adv3-{uuid.uuid4().hex[:8]}@example.com")
    headers["X-Workspace-Id"] = _new_workspace(c, headers, "adv-stale")
    doc_id = _upload_and_wait(
        c, headers, "old-policy.md",
        "# Legacy Expense Policy\n\nThe YANKEE-9910-LEGACY reimbursement cap is $500 per trip.\n",
    )
    # Backdate creation (and confirm never verified) so staleness -> 1.0.
    subprocess.run(
        [
            "docker", "exec", "-i", "atlaskb-postgres-1", "psql", "-U", "atlaskb", "-d", "atlaskb", "-c",
            f"UPDATE documents SET created_at = now() - interval '200 days' WHERE id = '{doc_id}';",
        ],
        check=True, capture_output=True,
    )

    r = c.post("/chat", headers=headers, json={"question": "What is the reimbursement cap in the legacy expense policy?"})
    r.raise_for_status()
    data = r.json()
    stale_evidence = any(e["staleness"] > 0.5 for e in data.get("evidence") or [])
    answer_lower = (data["answer"] or "").lower()
    caveat_words = ["stale", "outdated", "unverified", "not been verified", "may be out of date", "old", "hasn't been verified", "has not been verified"]
    answer_caveats = any(w in answer_lower for w in caveat_words)
    passed = stale_evidence and answer_caveats
    return {
        "name": "stale_source",
        "pass": passed,
        "detail": {
            "stale_evidence_shown": stale_evidence,
            "answer_contains_caveat": answer_caveats,
            "evidence_staleness": [e["staleness"] for e in data.get("evidence") or []],
            "answer": data["answer"],
        },
    }


def test_version_specific_question(c: httpx.Client) -> dict:
    """4. Asking about a historical version explicitly must not be silently
    upgraded to the current version's content."""
    headers = _signup_login(c, f"eval-adv4-{uuid.uuid4().hex[:8]}@example.com")
    headers["X-Workspace-Id"] = _new_workspace(c, headers, "adv-version")
    doc_id = _upload_and_wait(
        c, headers, "vacation-policy.md",
        "# Vacation Policy\n\nAs of March 2024, employees get 10 vacation days per year.\n",
    )
    r = c.post(
        f"/documents/{doc_id}/reupload", headers=headers,
        files={"file": ("vacation-policy.md", b"# Vacation Policy\n\nAs of 2026, employees get 15 vacation days per year.\n", "text/markdown")},
    )
    r.raise_for_status()
    for _ in range(30):
        d = c.get(f"/documents/{doc_id}", headers=headers).json()
        if d["status"] != "processing":
            break
        time.sleep(1)

    r = c.post("/chat", headers=headers, json={"question": "What did the March 2024 vacation policy say the number of vacation days was?"})
    r.raise_for_status()
    data = r.json()
    answer_lower = (data["answer"] or "").lower()
    mentions_old_value = "10" in answer_lower
    mentions_new_value_only = "15" in answer_lower and "10" not in answer_lower
    passed = mentions_old_value and not mentions_new_value_only
    return {
        "name": "version_specific_question",
        "pass": passed,
        "detail": {
            "answer": data["answer"],
            "mentions_old_value_10": mentions_old_value,
            "silently_upgraded_to_15_only": mentions_new_value_only,
        },
    }


def test_permission_leakage(c: httpx.Client) -> dict:
    """5. Reuses T9.1's dedicated, rigorous ACL check: the restricted chunk ID
    itself must never appear in a lower-privileged member's retrieved
    results, and a non-member must be rejected outright."""
    result = check_permission_leakage(c)
    return {"name": "permission_leakage", "pass": result["pass"], "detail": result}


def test_multi_hop(c: httpx.Client) -> dict:
    """6. A question requiring 2+ documents must retrieve from both, with
    claim-level (not one blanket) citations."""
    headers = _signup_login(c, f"eval-adv6-{uuid.uuid4().hex[:8]}@example.com")
    headers["X-Workspace-Id"] = _new_workspace(c, headers, "adv-multihop")
    _upload_and_wait(
        c, headers, "architecture.md",
        "# AtlasKB Architecture\n\nAtlasKB uses pgvector for dense retrieval and Postgres full-text search for sparse retrieval, fused with Reciprocal Rank Fusion.\n",
    )
    _upload_and_wait(
        c, headers, "billing.md",
        "# AtlasKB Billing\n\nThe AtlasKB free tier includes 100 queries per month.\n",
    )

    r = c.post(
        "/chat", headers=headers,
        json={"question": "What retrieval method does AtlasKB use, and how many free queries does it include per month?"},
    )
    r.raise_for_status()
    data = r.json()
    chunk_doc = {ch["chunk_id"]: ch["document_id"] for ch in data["retrieved"]}
    cited_docs = {
        chunk_doc.get(cid) for cit in data["citations"] for cid in cit["chunk_ids"]
    }
    two_docs_cited = len(cited_docs - {None}) >= 2
    multiple_citation_entries = len(data["citations"]) >= 2
    passed = two_docs_cited and multiple_citation_entries
    return {
        "name": "multi_hop",
        "pass": passed,
        "detail": {
            "answer": data["answer"],
            "citations": data["citations"],
            "distinct_docs_cited": len(cited_docs - {None}),
            "citation_entries": len(data["citations"]),
        },
    }


def test_claim_citation_coverage(c: httpx.Client) -> dict:
    """7. A multi-claim answer must have each claim carry its own citation,
    not one blanket citation list for the whole answer."""
    from run_before_after import citation_coverage

    headers = _signup_login(c, f"eval-adv7-{uuid.uuid4().hex[:8]}@example.com")
    headers["X-Workspace-Id"] = _new_workspace(c, headers, "adv-coverage")
    _upload_and_wait(
        c, headers, "spec.md",
        "# Falcon Spec\n\nThe Falcon Arm v2 has a reach of 900mm. It has a payload of 12kg. It draws 48V DC power.\n",
    )
    r = c.post(
        "/chat", headers=headers,
        json={"question": "What is the Falcon Arm v2's reach, payload, and power draw?"},
    )
    r.raise_for_status()
    data = r.json()
    coverage = citation_coverage(data["answer"], data["citations"]) if data["answerable"] else None
    multiple_citations = len(data["citations"]) >= 2
    passed = coverage is not None and coverage >= 0.5 and multiple_citations
    return {
        "name": "claim_citation_coverage",
        "pass": passed,
        "detail": {
            "answer": data["answer"],
            "citations": data["citations"],
            "coverage": coverage,
            "citation_entries": len(data["citations"]),
        },
    }


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=120) as c:
        tests = [
            test_no_answer,
            test_conflicting_sources,
            test_stale_source,
            test_version_specific_question,
            test_permission_leakage,
            test_multi_hop,
            test_claim_citation_coverage,
        ]
        results = []
        for fn in tests:
            print(f"running {fn.__name__}…")
            try:
                result = fn(c)
            except Exception as exc:  # noqa: BLE001 - a setup error is still a fail, not a crash
                result = {"name": fn.__name__, "pass": False, "detail": {"error": str(exc)}}
            status = "PASS" if result["pass"] else "FAIL"
            print(f"  [{status}] {result['name']}")
            results.append(result)

    passed = sum(1 for r in results if r["pass"])
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "adversarial.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\n=== {passed}/{len(results)} passed ===")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
