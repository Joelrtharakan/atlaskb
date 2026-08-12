# Eval harness & component-toggle flags (Trust Layer T9)

This directory holds the retrieval-QA eval (`run_eval.py` + `dataset.json` +
`corpus/`) and, as of T9, the flags used to run before/after and ablation
comparisons against the same harness.

## Component-toggle flags

Set these as environment variables (or in `.env`) **before starting the API
process** — they are read once at settings-load time via `app/config.py`.
They are not request-time overrides and are never exposed to real users; the
only way to change them is to restart the backend with different env vars,
which is exactly what the before/after and ablation runs below do between
passes.

| Flag | Values | Default | What it actually does |
|---|---|---|---|
| `RETRIEVAL_MODE` | `hybrid` \| `dense_only` \| `sparse_only` | `hybrid` | `hybrid`: dense + sparse, fused with RRF. `dense_only`: the sparse/BM25 SQL query and RRF fusion never run — `sparse_score` is `null` on every result. `sparse_only`: the dense pgvector query *and the query-embedding call* never run — `dense_score` is `null` on every result and no embedding cost is paid. |
| `RERANK_ENABLED` | `true` \| `false` | `true` | `true`: the cross-encoder re-scores the fused/single-mode candidate pool before the final top_k is chosen (Phase T3). `false`: the fused/single-mode order is final; no cross-encoder call is made, `rerank_score` is `null` on every result. |
| `VERSION_AWARE_RETRIEVAL` | `true` \| `false` | `true` | `true`: retrieval only ever returns chunks from each document's *current* version (Phase T1). `false`: reproduces pre-T1 behavior — every version's chunks are searchable at once, including superseded ones. |
| `CONFLICT_DETECTION_ENABLED` | `true` \| `false` | `true` | `true`: `/chat` runs the cross-document conflict check (Phase T4) whenever an answer cites 2+ documents. `false`: that LLM call never happens at all — `conflicts` is always `[]`, and it costs zero extra tokens/latency. |

All four are independent — any combination is valid. Verify a given
combination actually changed behavior by checking the `retrieval.hybrid_search`
log line's `mode`/`dense_candidates`/`sparse_candidates`/`rerank_enabled`/
`version_aware` fields, not just the config you *intended* to set.

## Named configurations

These are the specific combinations T9.1 (before/after) and T9.2 (ablation)
use, so later runs can cite a name instead of re-deriving the flag set.

**T9.1 before/after:**

| Name | RETRIEVAL_MODE | RERANK_ENABLED | VERSION_AWARE_RETRIEVAL | CONFLICT_DETECTION_ENABLED |
|---|---|---|---|---|
| `before` (pre-Trust-Layer) | `hybrid` | `false` | `false` | `false` |
| `after` (current system) | `hybrid` | `true` | `true` | `true` |

**T9.2 ablation (A→E):**

| Name | RETRIEVAL_MODE | RERANK_ENABLED | VERSION_AWARE_RETRIEVAL | CONFLICT_DETECTION_ENABLED |
|---|---|---|---|---|
| A — dense only | `dense_only` | `false` | `true` | `false` |
| B — dense + sparse, no RRF | *(not isolable as a flag — see note below)* | | | |
| C — hybrid (dense+sparse+RRF) | `hybrid` | `false` | `true` | `false` |
| D — C + reranking | `hybrid` | `true` | `true` | `false` |
| E — full Trust Layer | `hybrid` | `true` | `true` | `true` |

**Note on configuration B**: dense+sparse merged *without* RRF (e.g. by raw
score concatenation or max-score merge) is not a real code path anywhere in
this system — RRF is the only fusion strategy that was ever implemented, so
there is no flag for "hybrid without RRF" to toggle. Per T9.2's own
instruction to "note this limitation" rather than fabricate an isolation that
doesn't exist, configuration B is reported as **not applicable** in the
ablation results, not estimated or faked.

## Running a configuration

```bash
# from repo root
RETRIEVAL_MODE=dense_only RERANK_ENABLED=false VERSION_AWARE_RETRIEVAL=true CONFLICT_DETECTION_ENABLED=false \
  uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000 &

uv run --project apps/api python eval/run_eval.py
```

`run_eval.py` uploads `corpus/*.md` fresh into a throwaway eval workspace and
runs every question in `dataset.json` against whatever backend is listening at
`API_BASE` (default `http://127.0.0.1:8000`) — so the flags above take effect
purely from how that backend process was started.
