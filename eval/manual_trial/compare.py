#!/usr/bin/env python3
"""Generate a before/after comparison from results/before.json + results/after.json.

Writes AFTER_COMPARISON.md: pass-rate tables by root-cause layer and by original
question group, plus the per-question verdict flips. Safe to run standalone (e.g.
from the detached auto-resume script) so the comparison exists even if the
interactive session has ended.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"

VERDICTS = ["pass", "partial", "fail", "manual", "blocked"]


def load(name: str) -> dict:
    p = RES / name
    return json.loads(p.read_text()) if p.exists() else {"records": []}


def index(data: dict) -> dict[str, dict]:
    return {r["id"]: r for r in data.get("records", [])}


def rate(records: list[dict]) -> str:
    n = len(records)
    p = sum(1 for r in records if r["verdict"] == "pass")
    b = sum(1 for r in records if r["verdict"] == "blocked")
    return f"{p}/{n}" + (f" ({b} blocked)" if b else "")


def main() -> None:
    before, after = load("before.json"), load("after.json")
    bi, ai = index(before), index(after)
    all_ids = list(dict.fromkeys(list(bi) + list(ai)))

    by_layer_b: dict[str, list] = defaultdict(list)
    by_layer_a: dict[str, list] = defaultdict(list)
    by_group_b: dict[str, list] = defaultdict(list)
    by_group_a: dict[str, list] = defaultdict(list)
    for r in before.get("records", []):
        by_layer_b[r["layer"]].append(r); by_group_b[r["group"]].append(r)
    for r in after.get("records", []):
        by_layer_a[r["layer"]].append(r); by_group_a[r["group"]].append(r)

    lines: list[str] = []
    lines.append("# Before / After comparison\n")
    lines.append(f"- before: `{before.get('phase')}`  generated {before.get('generated_at')}")
    lines.append(f"- after:  `{after.get('phase')}`  generated {after.get('generated_at')}\n")

    lines.append("## By root-cause layer\n")
    lines.append("| Layer | Before | After |")
    lines.append("|---|---|---|")
    for layer in sorted(set(by_layer_b) | set(by_layer_a)):
        lines.append(f"| {layer} | {rate(by_layer_b.get(layer, []))} | {rate(by_layer_a.get(layer, []))} |")

    lines.append("\n## By question group\n")
    lines.append("| Group | Before | After |")
    lines.append("|---|---|---|")
    for group in sorted(set(by_group_b) | set(by_group_a)):
        lines.append(f"| {group} | {rate(by_group_b.get(group, []))} | {rate(by_group_a.get(group, []))} |")

    lines.append("\n## Per-question verdict changes\n")
    lines.append("| ID | Group | Before | After | After reason |")
    lines.append("|---|---|---|---|---|")
    for qid in all_ids:
        b = bi.get(qid, {}).get("verdict", "-")
        a = ai.get(qid, {}).get("verdict", "-")
        if b == a:
            continue
        grp = (ai.get(qid) or bi.get(qid) or {}).get("group", "")
        reason = (ai.get(qid) or {}).get("reason", "")[:80]
        lines.append(f"| {qid} | {grp} | {b} | {a} | {reason} |")

    lines.append("\n## Overall\n")
    lines.append(f"- before: {before.get('summary', {}).get('overall')}")
    lines.append(f"- after:  {after.get('summary', {}).get('overall')}")

    out = HERE / "AFTER_COMPARISON.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
