#!/usr/bin/env python3
"""Manual-trial evaluation harness for the Northwind Robotics corpus.

Runs a fixed question set against the *real* /search and /chat endpoints,
maintains conversation_id across multi-turn threads, authenticates as the
correct role per question, logs full request/response, and judges each result
against a ground-truth-aware rubric (pass / partial / fail / manual / blocked).

Auth: mints access-token JWTs directly with the repo JWT_SECRET (avoids needing
user passwords). Workspace/role are resolved server-side from the membership.

Usage:
  python harness.py --phase before        # run everything, write results/before.json
  python harness.py --phase after
  python harness.py --phase after --only search,pdf
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import requests

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- env
def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


ENV = load_env(REPO / ".env")
JWT_SECRET = ENV.get("JWT_SECRET", "")
JWT_ALG = ENV.get("JWT_ALGORITHM", "HS256")
CONFIG = json.loads((HERE / "config.json").read_text())
QUESTIONS = json.loads((HERE / "questions.json").read_text())
SHORTNAMES = QUESTIONS["meta"]["doc_shortnames"]  # short -> filename


def token_for(role: str) -> str:
    uid = CONFIG["principals"][role]
    now = datetime.now(UTC)
    payload = {"sub": uid, "type": "access", "iat": int(now.timestamp()),
               "exp": int((now + timedelta(minutes=30)).timestamp())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def headers_for(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(role)}",
            "X-Workspace-Id": CONFIG["workspace_id"],
            "Content-Type": "application/json"}


# --------------------------------------------------------- document id -> short
def build_id_map() -> dict[str, str]:
    """Map document_id -> shortname by listing documents as admin."""
    r = requests.get(f"{CONFIG['api_base']}/documents", headers=headers_for("admin"), timeout=30)
    r.raise_for_status()
    fname_to_short = {v: k for k, v in SHORTNAMES.items()}
    out = {}
    for d in r.json():
        out[d["id"]] = fname_to_short.get(d["filename"], d["filename"])
    return out


ID2SHORT: dict[str, str] = {}


def sources_of(results: list[dict]) -> list[str]:
    return [ID2SHORT.get(c.get("document_id"), c.get("document_id")) for c in results]


# --------------------------------------------------------------------- matching
def contains_token(text: str, needle: str) -> bool:
    """Substring match, but numeric needles match on numeric boundaries so
    '20' does not match inside '2024' and '100' not inside '1000'."""
    t = text.lower()
    n = needle.lower()
    if re.fullmatch(r"[\d.]+%?", n):
        core = n.rstrip("%")
        return re.search(r"(?<![\d.])" + re.escape(core) + r"(?![\d.])", t) is not None
    return n in t


def all_present(text: str, needles: list[str]) -> bool:
    return all(contains_token(text, x) for x in needles)


def any_group_ok(text: str, groups: list[list[str]]) -> bool:
    """Each group is satisfied if ANY of its members is present; ALL groups must
    be satisfied."""
    return all(any(contains_token(text, x) for x in group) for group in groups)


REFUSAL_MARKERS = ["cannot", "can't", "not able", "unable", "no information",
                   "don't have", "do not have", "not found", "not available",
                   "no relevant", "not able to", "restricted", "no document",
                   "cannot answer", "not contain", "isn't available", "not shared"]


# --------------------------------------------------------------------- endpoints
def call_search(query: str, role: str, top_k: int) -> dict:
    r = requests.post(f"{CONFIG['api_base']}/search",
                      headers=headers_for(role),
                      json={"query": query, "top_k": top_k}, timeout=60)
    return {"status": r.status_code, "body": _safe_json(r)}


def call_chat(query: str, role: str, top_k: int, conversation_id: str | None) -> dict:
    payload = {"question": query, "top_k": top_k}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    r = requests.post(f"{CONFIG['api_base']}/chat",
                      headers=headers_for(role),
                      json=payload, timeout=180)
    return {"status": r.status_code, "body": _safe_json(r)}


def _safe_json(r):
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:2000]}


INFRA_STATUSES = {402, 429, 502, 503, 504}


# --------------------------------------------------------------------- judging
def judge_search(j: dict, resp: dict) -> tuple[str, str]:
    if resp["status"] in INFRA_STATUSES:
        return "blocked", f"infra status {resp['status']}"
    if resp["status"] != 200:
        return "fail", f"HTTP {resp['status']}: {str(resp['body'])[:200]}"
    results = resp["body"].get("results", [])
    srcs = sources_of(results)
    typ = j["type"]

    if typ == "search_topk":
        top = srcs[: j.get("rank", 3)]
        want = j["expect_any_source"]
        ok = any(s in want for s in top)
        gap = ""
        if len(results) >= 2:
            gap = f" | top score {results[0].get('score', 0):.4f} vs #2 {results[1].get('score', 0):.4f}"
        return ("pass" if ok else "fail"), f"top{j.get('rank',3)} sources={top} want-any={want}{gap}"

    if typ == "search_multi":
        distinct = list(dict.fromkeys(srcs))
        ok = len(distinct) >= j["min_distinct_sources"]
        return ("pass" if ok else "fail"), f"distinct sources={distinct}"

    if typ == "search_absent":
        if not results:
            return "pass", "no results returned"
        max_dense = max((c.get("dense_score") or 0) for c in results)
        top_src = srcs[0] if srcs else "-"
        ok = max_dense < j["max_dense_score"]
        verdict = "pass" if ok else "partial"
        return verdict, f"max dense_score={max_dense:.4f} (thr {j['max_dense_score']}), top src={top_src}"

    if typ == "search_acl_exclude":
        forbidden = set(j["forbidden_sources"])
        leaked = [s for s in srcs if s in forbidden]
        ok = not leaked
        return ("pass" if ok else "fail"), (f"restricted excluded (sources={list(dict.fromkeys(srcs))})"
                                            if ok else f"LEAK: restricted doc in results {srcs}")
    return "manual", "unknown judge type"


def judge_chat(j: dict, resp: dict) -> tuple[str, str]:
    if resp["status"] in INFRA_STATUSES:
        return "blocked", f"infra status {resp['status']} (LLM provider / rate limit)"
    if resp["status"] != 200:
        return "fail", f"HTTP {resp['status']}: {str(resp['body'])[:200]}"
    body = resp["body"]
    answer = body.get("answer", "") or ""
    answerable = bool(body.get("answerable"))
    ncit = len(body.get("citations", []) or [])
    typ = j["type"]
    tail = f" | answerable={answerable} cites={ncit}"

    if typ == "chat_contains":
        if j.get("answerable") is True and not answerable:
            return "fail", "expected an answer but got not-answerable" + tail
        conds = []
        if j.get("all_of"):
            conds.append(all_present(answer, j["all_of"]))
        if j.get("any_of"):
            conds.append(any_group_ok(answer, j["any_of"]))
        if j.get("also_any_of"):
            conds.append(any_group_ok(answer, j["also_any_of"]))
        ok = all(conds) if conds else answerable
        return ("pass" if ok else "fail"), f"text-match={ok}" + tail

    if typ == "chat_false_premise":
        bad = [x for x in j.get("must_not_contain", []) if contains_token(answer, x)]
        corrected = (not answerable) or any(contains_token(answer, x) for x in j.get("accept_any_of", []))
        if bad:
            return "fail", f"fabricated / leaked: {bad}" + tail
        return ("pass" if corrected else "partial"), (
            "corrected/declined false premise" if corrected else "did not clearly correct premise") + tail

    if typ == "chat_refuse":
        bad = [x for x in j.get("must_not_contain", []) if contains_token(answer, x)]
        if bad:
            return "fail", f"LEAKED restricted values: {bad}" + tail
        refused = (not answerable) or any(m in answer.lower() for m in REFUSAL_MARKERS)
        return ("pass" if refused else "partial"), (
            "refused with no leakage" if refused else "no leak but did not clearly refuse") + tail

    if typ == "chat_manual":
        hint = any(contains_token(answer, x) for x in j.get("hint_any_of", []))
        return "manual", f"HINT_MATCH={hint} (needs human confirmation)" + tail

    return "manual", "unknown judge type" + tail


# --------------------------------------------------------------------- runner
def run(phase: str, only: set[str]) -> None:
    global ID2SHORT
    ID2SHORT = build_id_map()
    records: list[dict] = []
    top_k = CONFIG["top_k"]

    def log(rec: dict) -> None:
        records.append(rec)
        v = rec["verdict"].upper()
        print(f"  [{v:7}] {rec['id']:16} {rec['reason'][:110]}")

    # ---- /search ----
    if "search" in only:
        print("\n=== /search ===")
        for q in QUESTIONS["search"]:
            resp = call_search(q["query"], q["role_context"], top_k)
            verdict, reason = judge_search(q["judge"], resp)
            log({"section": "search", "id": q["id"], "group": q["group"], "layer": q["layer"],
                 "role": q["role_context"], "query": q["query"],
                 "expected_behavior": q["expected_behavior"],
                 "verdict": verdict, "reason": reason,
                 "response": _trim_search(resp)})
            time.sleep(0.3)

    # ---- /chat threads (multi-turn, shared conversation_id) ----
    if "chat" in only:
        print("\n=== /chat threads ===")
        for thread in QUESTIONS["chat_threads"]:
            conv_id = None
            print(f"-- thread {thread['id']} ({thread['group']}) as {thread['role_context']}")
            for turn in thread["turns"]:
                resp = call_chat(turn["query"], thread["role_context"], top_k, conv_id)
                if resp["status"] == 200:
                    conv_id = resp["body"].get("conversation_id", conv_id)
                verdict, reason = judge_chat(turn["judge"], resp)
                log({"section": "chat", "id": turn["id"], "thread": thread["id"],
                     "group": thread["group"], "layer": thread["layer"],
                     "role": thread["role_context"], "query": turn["query"],
                     "conversation_id": conv_id,
                     "expected_behavior": turn["expected_behavior"],
                     "verdict": verdict, "reason": reason,
                     "response": _trim_chat(resp)})
                time.sleep(0.8)

    # ---- PDF-specific (single-shot) ----
    if "pdf" in only:
        print("\n=== PDF-specific ===")
        for q in QUESTIONS["pdf"]:
            if q["endpoint"] == "chat":
                resp = call_chat(q["query"], q["role_context"], top_k, None)
                verdict, reason = judge_chat(q["judge"], resp)
                response = _trim_chat(resp)
            else:
                resp = call_search(q["query"], q["role_context"], top_k)
                verdict, reason = judge_search(q["judge"], resp)
                response = _trim_search(resp)
            log({"section": "pdf", "id": q["id"], "group": q["group"], "layer": q["layer"],
                 "role": q["role_context"], "query": q["query"],
                 "expected_behavior": q["expected_behavior"],
                 "verdict": verdict, "reason": reason, "response": response})
            time.sleep(0.8)

    out = {"phase": phase, "generated_at": datetime.now(UTC).isoformat(),
           "config": {"workspace_id": CONFIG["workspace_id"], "top_k": top_k},
           "records": records, "summary": summarize(records)}
    path = RESULTS_DIR / f"{phase}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nWrote {path}")
    print_summary(out["summary"])


def _trim_search(resp: dict) -> dict:
    if resp["status"] != 200:
        return resp
    res = resp["body"].get("results", [])
    return {"status": 200, "cached": resp["body"].get("cached"),
            "results": [{"src": ID2SHORT.get(c.get("document_id"), c.get("document_id")),
                         "page": c.get("page_num"), "score": round(c.get("score", 0), 5),
                         "dense": round(c.get("dense_score") or 0, 4),
                         "sparse": round(c.get("sparse_score") or 0, 4),
                         "text": (c.get("text") or "")[:180]} for c in res]}


def _trim_chat(resp: dict) -> dict:
    if resp["status"] != 200:
        return resp
    b = resp["body"]
    return {"status": 200, "answerable": b.get("answerable"), "answer": b.get("answer"),
            "citations": b.get("citations"), "queries": b.get("queries"),
            "iterations": b.get("iterations"), "cached": b.get("cached"),
            "retrieved_sources": list(dict.fromkeys(sources_of(b.get("retrieved", []))))}


def summarize(records: list[dict]) -> dict:
    def tally(items):
        c = {"pass": 0, "partial": 0, "fail": 0, "manual": 0, "blocked": 0}
        for r in items:
            c[r["verdict"]] = c.get(r["verdict"], 0) + 1
        return c
    by_layer: dict[str, list] = {}
    by_group: dict[str, list] = {}
    for r in records:
        by_layer.setdefault(r["layer"], []).append(r)
        by_group.setdefault(r["group"], []).append(r)
    return {"overall": tally(records),
            "by_layer": {k: tally(v) for k, v in by_layer.items()},
            "by_group": {k: tally(v) for k, v in by_group.items()}}


def print_summary(summary: dict) -> None:
    print("\n===== SUMMARY =====")
    o = summary["overall"]
    print(f"overall: {o}")
    print("\nby root-cause layer:")
    for k, v in sorted(summary["by_layer"].items()):
        print(f"  {k:16} {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--only", default="search,chat,pdf")
    args = ap.parse_args()
    if not JWT_SECRET:
        print("JWT_SECRET not found in .env", file=sys.stderr)
        sys.exit(1)
    run(args.phase, set(s.strip() for s in args.only.split(",")))
