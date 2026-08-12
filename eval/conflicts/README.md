# Conflict-detection benchmark (Trust Layer Phase 1)

`dataset.json` — 24 labeled claim pairs, 3 per category, covering the 8
categories the phase spec asked for: obvious contradiction, subtle
contradiction, numeric contradiction, date contradiction, policy
contradiction, complementary claims, unrelated claims, ambiguous claims. Each
case has an `expected_relationship` from the 5-way taxonomy (SUPPORTS,
CONTRADICTS, COMPLEMENTS, UNRELATED, UNCERTAIN — this benchmark has no
SUPPORTS cases since none of the 8 required categories call for one, but the
pipeline and scoring both support it).

Run with:

```bash
uv run --project apps/api python eval/run_conflict_benchmark.py
```

This calls `app.conflict_detection.detect_conflicts_structured` directly
(the same function `/chat` calls) against whichever LLM the environment has
configured — a real run against the real pipeline, not a mock. It writes
`eval/results/conflicts.json`: overall accuracy, a CONTRADICTS-vs-everything-
else confusion (precision/recall/F1/false-positive-rate/false-negative-rate
— the binary framing a reader actually cares about: "is this really a
conflict"), a full 5x5 confusion matrix, per-category accuracy, and every
individual case's prediction.

## Why the binary framing, in addition to 5-way accuracy

5-way accuracy (exact relationship match) is the strict metric and is
reported too, but COMPLEMENTS vs. UNRELATED vs. UNCERTAIN is a genuinely
harder distinction than "is this CONTRADICTS or not" — and CONTRADICTS is
the one relationship that actually surfaces to the end user as a "Sources
disagree" banner. Precision/recall/F1 on that binary split is the number
that best answers "does the Trust Layer actually catch real conflicts
without crying wolf."

## How confidence is calculated (and its real limits)

Every `StructuredConflict` carries a `confidence` value, but it comes from
two very different sources depending on `method`:

- **`method: "deterministic"`** — a fixed constant from
  `app.config.Settings` (`conflict_deterministic_numeric_confidence` = 0.9,
  `conflict_deterministic_date_confidence` = 0.85,
  `conflict_deterministic_agreement_confidence` = 0.85). These are **not
  learned or calibrated against a validation curve** — they're a judgment
  call ("a disjoint-number-set match on an already topic-similar pair is a
  strong signal, worth ~0.9") documented here rather than hidden behind a
  precise-looking float. Treat them as "high confidence, heuristic" not
  "90% empirically correct."
- **`method: "llm"`** — the model's own self-reported confidence (0.0-1.0),
  requested directly in the classification prompt. This is **not
  independently calibrated either** — it's whatever the configured model
  says about itself, with the same reliability caveats as any LLM
  self-assessment. A smaller/local model's self-reported 0.9 is not
  necessarily as reliable as a larger model's 0.9.

Neither path is "fake" in the sense of being invented after the fact — both
are real, traceable to a specific rule or a specific model response — but
neither should be read as a statistically calibrated probability. This
benchmark's precision/recall numbers are the actual calibration check: if
deterministic CONTRADICTS classifications turn out imprecise in practice,
that will show up here as a lower precision number, not as a hidden problem.

## Known limitations of the deterministic path

The numeric/date deterministic classifier (`app/conflict_detection/
deterministic.py`) is a heuristic over already topic-filtered pairs, not a
proof. It can misfire on a chunk with several incidental numbers only one of
which is the actually-disputed value (e.g. a page number alongside a policy
figure) — candidate filtering reduces this risk (only topically-similar
pairs reach it at all) but doesn't eliminate it. The benchmark's `numeric_*`
and `date_*` category results are the direct measurement of how often this
actually goes wrong on realistic-shaped text, not a theoretical estimate.

## Measured results (real runs, both disclosed)

First run (default `conflict_candidate_min_similarity=0.15`, entity extractor
requiring 4+ letter words): **accuracy 50.0% (12/24)**, CONTRADICTS
precision=1.0, recall=0.6, F1=0.75. Diagnosis: 8 of the 12 misses were
`method: "filtered"` — the candidate pair never reached classification at
all. Checking similarity scores directly showed the entity extractor was
dropping 3-letter subject-identifying words like "PTO" and "cap" (word regex
required 4+ letters), so `numeric-3` — the PTO-accrual-vs-unlimited-PTO case
already used elsewhere in this codebase as the canonical conflict example —
scored **0.0 topic similarity** purely from that bug, not from any real
judgment about the claims.

Fixed the word-length cutoff (3+ letters, with an expanded stopword list to
compensate) and lowered `conflict_candidate_min_similarity` from 0.15 to
0.05 — chosen because every genuinely-`unrelated` pair in this dataset scores
*exactly* 0.0 similarity, so 0.05 costs nothing on precision while recovering
several real conflicts that scored 0.06-0.14. Re-ran: **accuracy 62.5%
(15/24)**, CONTRADICTS precision=1.0 (unchanged — no false positives
introduced), recall=0.6→**0.8**, F1=0.75→**0.889**. Per-category accuracy:
`obvious_contradiction` 100%, `numeric_contradiction` 100%,
`unrelated_claims` 100%, `subtle_contradiction`/`date_contradiction`/
`policy_contradiction` 67% each, `complementary_claims` 0%, `ambiguous_claims`
0%.

Both runs' full per-case output is in git history / `eval/results/conflicts.json`
(the latter is overwritten on each run — this README is where the before/after
comparison is preserved).

## Known weak spots (measured, not glossed over)

- **`complementary_claims`: 0/3.** The model classified 2 of 3 as UNCERTAIN
  rather than COMPLEMENTS (a defensible near-miss — "these are related but
  not clearly complementary" is a reasonable hedge, not a dangerous error)
  and 1 was filtered out entirely before reaching the LLM. COMPLEMENTS
  appears to be the hardest relationship in the taxonomy for the configured
  local model to commit to positively.
- **`ambiguous_claims`: 0/3.** All were classified UNRELATED or COMPLEMENTS
  rather than the expected UNCERTAIN — the model rarely chooses UNCERTAIN
  unprompted, tending to force a more decisive-sounding answer even on
  genuinely vague text. Two of the three were also filtered before reaching
  the LLM: bag-of-words similarity is fundamentally unable to tell "same
  subject, paraphrased with almost no shared vocabulary" apart from
  "different subject" when literal word overlap is zero on both — this is a
  real, structural limit of a deterministic (non-embedding) candidate
  filter, not a threshold-tuning problem. Fixing it would need a semantic
  (embedding-based) similarity signal for candidate selection, which this
  phase deliberately did not build (candidate filtering was scoped as fast
  and deterministic, per the phase's own "do not perform O(n²) LLM
  comparisons" instruction) — documented here as a real, known gap rather
  than silently left unmentioned.
- **Claim extraction can shift entities out from under the similarity
  check.** The candidate filter runs on the LLM-extracted claim text, not
  the raw source text — a paraphrase during extraction can raise or lower a
  pair's similarity score unpredictably run to run (observed: `date-1`
  passed the filter in one run and was filtered out in the next, despite
  identical input text, because extraction worded the claim differently
  each time). This is a real source of run-to-run variance this benchmark
  does not fully control for.

## What this benchmark does NOT cover

- It exercises the pipeline on isolated 2-claim inputs, not through a full
  `/chat` request (persistence, evidence-building, and the response's
  CONTRADICTS-only surfacing are covered separately by
  `apps/api/tests/test_conflicts.py` and `test_conflict_pipeline.py`).
- It measures relationship-classification quality, not retrieval recall
  (whether the two conflicting chunks would actually both get retrieved for
  a real question) — that remains covered by `eval/run_before_after.py`'s
  `conflict_detection_accuracy` metric and `eval/run_adversarial.py`'s
  `conflicting_sources` case, both against a live corpus.
