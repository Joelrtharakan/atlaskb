# Expanded evaluation (Trust Layer Phase 3) — honest scope

The phase spec's target was 300 questions across retrieval, answer quality,
citations, trust, security, temporal, and failure-case categories. **This
pass does not reach 300.** Disclosed plainly rather than padded to look
complete:

- `eval/dataset_expanded.json` adds **26 new categorized questions**
  (retrieval: direct lookup/semantic/keyword/multi-hop/cross-document,
  answer quality, citations, trust/conflicts) on top of the existing 17 in
  `eval/dataset.json` (kept unchanged, still run by `eval/run_eval.py`) —
  **43 real QA cases total**, each with a real expected answer grounded in
  real corpus content, not filler.
- 5 new corpus documents (`northwind-security-policy.md`,
  `northwind-incident-response.md`, `northwind-expense-policy.md`,
  `northwind-vendor-management.md`, `northwind-benefits-guide.md`) were
  added specifically to give the multi-hop and cross-document categories
  real material to work with (e.g. "what security standard must a vendor
  meet" spans the vendor-management and security-policy documents).
- Security, temporal, and staleness categories are **not** expressed as
  static QA pairs — they need live setup a labeled question list can't
  describe (backdating a document's `created_at`, a real reupload creating
  real version history, two genuinely separate workspaces). These are
  implemented as **5 dedicated pass/fail checks** in
  `eval/run_expanded_eval.py` instead: ACL bypass (reuses
  `run_before_after.check_permission_leakage` rather than reimplementing
  it), cross-tenant retrieval leakage, cached-answer workspace isolation,
  staleness actually reaching the model (real DB backdating + checking both
  `Evidence.staleness` and Phase 5's `trust_summary.source_freshness`), and
  a live version-comparison round-trip through `/chat`'s Phase 2 temporal
  path.
- Prompt-injection and indirect-injection security cases are **not**
  duplicated here — `eval/run_prompt_injection.py` already covers them
  (3/3, see `eval/results/prompt_injection.json`) and re-running the exact
  same fixtures under a different script name would inflate the count
  without adding real coverage.

## Why not just write 300 questions to hit the number

Every question in `dataset_expanded.json` has a real `expected_doc` and
real `expected_substrings` checked against a real corpus document — writing
300 of these responsibly means writing (or generating and manually
verifying) 300 real facts across a correspondingly large real corpus. Doing
that carelessly to hit a round number would violate this project's own
standing rule against fabricating measured results: a low-quality 300th
question graded against a made-up expected answer is worse than an honest
43. What's here is real and reproducible; getting to 300 for real is future
work, not a corner that was cut silently.

## Regression detection

`eval/run_expanded_eval.py` compares `answer_accuracy` / `retrieval_hit_rate`
/ `refusal_accuracy` against `eval/results/expanded_eval_baseline.json` (a
saved snapshot from the first successful run) and exits non-zero if any of
them drops by more than 10 percentage points — a rough per-run smoke check,
not a substitute for reading the actual numbers.

## Running it

```bash
uv run --project apps/api python eval/run_expanded_eval.py
```

Writes `eval/results/expanded_eval.json` (overwritten each run) and, on the
first run only, `eval/results/expanded_eval_baseline.json` (the regression
baseline — delete it to intentionally re-baseline after an expected change).
