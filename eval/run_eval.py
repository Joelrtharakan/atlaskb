#!/usr/bin/env python
"""AtlasKB retrieval-QA evaluation.

Runs a small labelled Q&A set (``dataset.json``) over a known corpus
(``corpus/``) against a *live* AtlasKB backend and reports grounded-RAG metrics:

  * answer_accuracy       — answerable questions whose answer contains the fact
  * citation_grounding    — answerable answers that cite the expected document
  * refusal_accuracy      — out-of-corpus questions correctly refused
  * retrieval_hit_rate    — expected document present in retrieved chunks
  * avg_tokens_per_query, latency p50/p95

Results are written to ``eval/results/latest.json`` (read by /admin/evals).

Usage (from repo root, backend running):
    set -a && . ./.env && set +a
    uv run python eval/run_eval.py
"""

from __future__ import annotations

import json
import os
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
OUT = HERE / "results" / "latest.json"
MODEL = os.environ.get("OPENROUTER_MODEL", "backend-configured")


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((p / 100) * len(ordered) + 0.5) - 1))
    return ordered[k]


def main() -> None:
    dataset = json.loads(DATASET.read_text())
    questions = dataset["questions"]

    with httpx.Client(base_url=BASE, timeout=120) as c:
        email = f"eval-{uuid.uuid4().hex[:10]}@example.com"
        password = "eval-password-123"
        c.post("/auth/signup", json={"email": email, "password": password}).raise_for_status()
        tokens = c.post("/auth/login", json={"email": email, "password": password}).json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Upload the corpus and wait until every document is ready.
        doc_by_id: dict[str, str] = {}
        for path in sorted(CORPUS.glob("*.md")):
            files = {"file": (path.name, path.read_bytes(), "text/markdown")}
            r = c.post("/documents", headers=headers, files=files)
            r.raise_for_status()
            doc_by_id[r.json()["id"]] = path.name
        print(f"uploaded {len(doc_by_id)} documents; waiting for ingestion…")

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
                if q["answerable"]
                else None
            )
            grounded = (
                (q["expected_doc"] in cited_docs) if (q["answerable"] and data["answerable"]) else None
            )
            refusal_correct = (data["answerable"] is False) if not q["answerable"] else None

            results.append(
                {
                    "question": q["question"],
                    "expected_doc": q["expected_doc"],
                    "answerable_expected": q["answerable"],
                    "answerable_actual": data["answerable"],
                    "retrieval_hit": hit,
                    "answer_correct": answered_correctly,
                    "citation_grounded": grounded,
                    "refusal_correct": refusal_correct,
                    "tokens": data.get("usage", {}).get("total", 0),
                    "latency_ms": round(dt, 1),
                    "answer": data["answer"],
                }
            )
            print(
                f"  {q['question'][:48]:50s} hit={hit} correct={answered_correctly} "
                f"grounded={grounded} refuse={refusal_correct} {dt:.0f}ms"
            )

    def rate(key: str, cond) -> float | None:
        relevant = [r for r in results if cond(r)]
        if not relevant:
            return None
        passed = sum(1 for r in relevant if r[key] is True)
        return round(passed / len(relevant), 3)

    metrics = {
        "answer_accuracy": rate("answer_correct", lambda r: r["answerable_expected"]),
        "citation_grounding": rate(
            "citation_grounded", lambda r: r["answerable_expected"] and r["answerable_actual"]
        ),
        "refusal_accuracy": rate("refusal_correct", lambda r: not r["answerable_expected"]),
        "retrieval_hit_rate": rate("retrieval_hit", lambda r: r["expected_doc"] is not None),
        "avg_tokens_per_query": round(statistics.mean(tokens_per_query), 1) if tokens_per_query else 0,
        "latency_p50_ms": round(pctl(latencies, 50), 1),
        "latency_p95_ms": round(pctl(latencies, 95), 1),
    }

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "dataset_size": len(questions),
        "corpus_size": len(list(CORPUS.glob("*.md"))),
        "metrics": metrics,
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print("\n=== metrics ===")
    print(json.dumps(metrics, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
