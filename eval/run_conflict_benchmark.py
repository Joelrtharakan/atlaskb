#!/usr/bin/env python
"""Labeled benchmark for the structured conflict-detection pipeline (Trust
Layer Phase 1) — eval/conflicts/dataset.json.

Runs the REAL pipeline (app.conflict_detection.detect_conflicts_structured)
against the backend's configured LLM (whatever LLM_PROVIDER/CONFLICT_DETECTION_MODEL
the environment has set) — not a mock. Each case is a pair of claims, each
wrapped as a one-chunk-per-document RetrievedChunk so the pipeline's claim
extraction, candidate filtering, deterministic classification, and LLM
classification stages all run exactly as they would in production.

Unlike eval/run_adversarial.py (HTTP against a running API), this imports
`app` directly — it doesn't need a running server, only a reachable LLM and
(for the local default) no database at all, since the pipeline itself never
touches Postgres (persistence is chat.py's job, not the pipeline's).

Usage (from repo root):
    uv run --project apps/api python eval/run_conflict_benchmark.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"

from app.conflict_detection import Relationship, detect_conflicts_structured  # noqa: E402
from app.retrieval import RetrievedChunk  # noqa: E402

RELATIONSHIPS = [r.value for r in Relationship]


def _chunk(cid: str, doc: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid, document_id=doc, version_id=None, text=text,
        page_num=None, section=None, score=1.0,
    )


def _predict(case: dict) -> tuple[str, str]:
    """Run the real pipeline over one claim pair.

    Returns (predicted_relationship, method). If the pair never becomes a
    candidate (filtered out by topic-similarity before classification even
    runs), the pipeline made no explicit call — its behavior is equivalent to
    "not flagged as any kind of match", scored as UNRELATED with method
    "filtered" since that's the closest of the 5 labels to "the system never
    even considered these related enough to compare."
    """
    chunk_a = _chunk("a", case["doc_a"], case["claim_a"])
    chunk_b = _chunk("b", case["doc_b"], case["claim_b"])
    results, _usage = detect_conflicts_structured([chunk_a, chunk_b])
    if not results:
        return "UNRELATED", "filtered"
    r = results[0]
    return r.relationship.value, r.method


def main() -> None:
    dataset = json.loads((HERE / "conflicts" / "dataset.json").read_text())
    cases = dataset["cases"]

    rows = []
    for case in cases:
        predicted, method = _predict(case)
        expected = case["expected_relationship"]
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "expected": expected,
                "predicted": predicted,
                "method": method,
                "correct": predicted == expected,
            }
        )
        print(f"  [{'OK' if predicted == expected else 'MISS'}] {case['id']:<16} "
              f"expected={expected:<12} predicted={predicted:<12} ({method})")

    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    accuracy = correct / total if total else 0.0

    # Binary framing (CONTRADICTS = positive class) for precision/recall/F1/
    # false-positive-rate/false-negative-rate, since "is this a real
    # contradiction" is the decision that actually matters to a reader.
    tp = sum(1 for r in rows if r["expected"] == "CONTRADICTS" and r["predicted"] == "CONTRADICTS")
    fp = sum(1 for r in rows if r["expected"] != "CONTRADICTS" and r["predicted"] == "CONTRADICTS")
    fn = sum(1 for r in rows if r["expected"] == "CONTRADICTS" and r["predicted"] != "CONTRADICTS")
    tn = sum(1 for r in rows if r["expected"] != "CONTRADICTS" and r["predicted"] != "CONTRADICTS")

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall and (precision + recall) else None
    false_positive_rate = fp / (fp + tn) if (fp + tn) else None
    false_negative_rate = fn / (fn + tp) if (fn + tp) else None

    by_category: dict[str, dict] = {}
    for r in rows:
        c = by_category.setdefault(r["category"], {"total": 0, "correct": 0})
        c["total"] += 1
        c["correct"] += int(r["correct"])
    for c in by_category.values():
        c["accuracy"] = c["correct"] / c["total"] if c["total"] else 0.0

    confusion: dict[str, dict[str, int]] = {e: {p: 0 for p in RELATIONSHIPS} for e in RELATIONSHIPS}
    for r in rows:
        confusion[r["expected"]][r["predicted"]] += 1

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_cases": total,
        "accuracy": round(accuracy, 3),
        "binary_contradicts_vs_rest": {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "precision": round(precision, 3) if precision is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "f1": round(f1, 3) if f1 is not None else None,
            "false_positive_rate": round(false_positive_rate, 3) if false_positive_rate is not None else None,
            "false_negative_rate": round(false_negative_rate, 3) if false_negative_rate is not None else None,
        },
        "by_category": by_category,
        "confusion_matrix": confusion,
        "cases": rows,
    }

    print()
    print(f"=== accuracy {accuracy:.1%} ({correct}/{total}) ===")
    print(f"=== CONTRADICTS precision={result['binary_contradicts_vs_rest']['precision']} "
          f"recall={result['binary_contradicts_vs_rest']['recall']} "
          f"f1={result['binary_contradicts_vs_rest']['f1']} ===")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "conflicts.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
