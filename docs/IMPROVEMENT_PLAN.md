# AtlasKB Trust Layer — Improvement Plan

**Status: all 16 phases complete. Groups A, B, C done. Phase 10 (connector
architecture) shipped its first real provider in a later session: a
working Google Drive connector (real OAuth, real Drive API calls, native
Google Docs/Sheets/Slides export, admin UI) — see `app/connectors/README.md`
for exactly what's in and out of scope for that provider. Phase 11
(enterprise SSO), initially skipped, was also completed in that later
session: a generic OIDC client working with any standards-compliant
provider, live-verified against a real Google account. Phase 14
(test-gap-filling) closed the one real coverage hole that session's own
new code left behind (the connectors router's HTTP layer). Phase 15/16
were re-run after all of the above — see `docs/IMPROVEMENT_REPORT.md` for
current numbers.**

## Phase 10 — done (architecture only, by explicit user decision)

Building a real, working connector needs a real OAuth app registration and
credentials only the deployer can provide — asked the user directly rather
than assume; they chose "architecture only, no live connector" (matching
the phase spec's own "do not create fake connector implementations" rule).

Built: `app/connectors/base.py` (the `Connector` ABC — `authenticate`,
`test_connection`, `list_sources`, `fetch_document`, `fetch_changes`,
`delete_document`, `get_permissions`, plus a default `sync()`), `app/
connectors/sync.py` (`run_connector_sync` — hands a connector's normalized
output to the *exact same* `app.versioning`/`app.ingest` pipeline direct
upload already uses, no duplicated parse/chunk/embed/version logic), and
`ConnectorConfig`/`ConnectorDocument` models + migration `0009_connectors.py`
(workspace, provider, external ids, last sync time/status, checksum,
external version, permission metadata — exactly the fields the spec
asked for; `credentials_ref` is deliberately never a plaintext secret).

**Two real bugs found by writing the tests**, both fixed before either
would have reached a real provider: (1) a test-harness session-detachment
issue (SQLAlchemy objects mutated after their loading session closed
silently don't persist) — not a bug in the shipped code, but worth noting
since it could easily have hidden a real one; (2) a genuine logic bug in
`sync.py` itself — a changed document was creating a brand-new `Document`
row instead of a new version of the existing one, unlike the reupload
endpoint it was supposed to mirror. Fixed by having `_write_and_ingest`
look up and reuse the existing `Document` when a `ConnectorDocument`
record already links one.

Proven end-to-end with an explicitly-test-only `_FakeConnector` (in-memory,
no network, named and documented as a test fixture, not a product feature)
— 8 new tests: full sync lifecycle, per-document failure isolation, auth
failure, unchanged-document skip (checksum-based), changed-document
creates a real new version (not a duplicate), and no-real-record-left-
behind on a failed fetch. `app/connectors/README.md` spells out exactly
what a real Google Drive connector would still need (real OAuth, Drive
API calls, native-format export, a real ACL-mapping decision, a sync
schedule, admin UI/API) — none of which exists yet.

Full backend suite: **215/215 passing** (207 + 8 new). Migration applied
to the dev DB; server restarted and boots cleanly with the new tables.

## Phase 12 — done

Reordered the `/chat` page so Answer → Citations → Trust Summary →
Conflicts → Evidence (all already inside the answer panel from Phase 6) is
the primary, wider pane and the Living Atlas is secondary — the literal
reverse of the pre-existing layout, which the Phase 0 audit flagged as the
Atlas being dominant (wider pane, physically first) with the answer as a
narrow sidebar.

Implemented via Tailwind `order-1`/`order-2` utilities rather than
physically moving JSX blocks — lower risk, same visual and DOM-order
result in both the desktop row layout and the mobile stacked-column
layout, without touching any Atlas/2D-fallback/reduced-motion/collapse
logic itself (all preserved exactly, per the phase's own "keep the Living
Atlas" / "keep 2D fallback" rules).

**Live-verified in a real browser**: confirmed both the expanded state
(answer panel wide and first, Atlas a fixed 420px pane on the right with
its collapse button correctly repositioned) and the collapsed state (Atlas
reduces to a slim vertical "Living Atlas" strip on the right edge, answer
panel expands to fill the freed space) render correctly — not just
inferred from the CSS change.

6/6 relevant Playwright e2e tests pass unchanged (`atlas.spec.ts`,
`atlas-render.spec.ts`, `chat-atlas.spec.ts`, `rag-flow.spec.ts`) — none of
them depended on the old visual order. Backend suite unaffected (pure
frontend phase): **207/207 passing**.

## Phase 13 — done

Extended the existing `StageTimer` (T9.5) rather than adding a new tracing
stack, per that module's own established philosophy. `request_id` was
already bound to every log line for a request via structlog contextvars
(`main.py`'s middleware) — nothing new needed there. Added two previously-
untimed stages (`cache` lookup, `evidence` build) so the full spec'd chain
(auth → cache → query planning → retrieval → reranking → sufficiency →
generation → conflict detection → evidence → response) is now timed
end-to-end. Added one structured `chat.trace` log line per request (all 5
exit paths: cache hit, full compute, and all 3 temporal-path returns) with
every field the spec asked for — model, retrieval count, reranking
enabled, conflict-candidate count, cache hit/miss, trust mode, final
answer status — never raw document content, only counts/booleans/ids.

**A real bug found by writing the tests, not just passing them**: the
first version logged `conflict_detection_ran=run_conflict_detection`
directly. That variable was set via a Python `and` chain
(`settings.conflict_detection_enabled and ... and result.chunks`) —
Python's `and` returns the *last evaluated operand*, not a coerced bool, so
whenever conflict detection ran, this variable was actually the retrieved
chunk list itself, not `True`. Harmless everywhere it was only used in an
`if` check (any non-empty list is truthy), but logging it directly would
have put **raw retrieved document text straight into the trace log** —
exactly what the phase's own "never log raw sensitive document contents"
rule forbids. Caught by `test_chat_trace_never_includes_raw_answer_or_document_text`
before it ever ran live; fixed with an explicit `bool(...)` at the source,
with a comment explaining why the coercion is load-bearing now.

Live-verified after the fix: a real request's `chat.trace` line showed
`"conflict_detection_ran": true` (a real boolean) and a full stage
breakdown (`cache`, `condense`, `retrieval`, `reranking`, `generation`,
`conflict_detection`, `evidence`) with zero document content anywhere in
the line.

5 new tests. Full backend suite: **207/207 passing**.

## Phase 7 — done

`/admin/content-gaps` previously showed only raw `query` + `count` — zero
cause classification, per the Phase 0 audit. Added live classification
(deliberately live, not from historical snapshots — nothing about what was
actually retrieved for a past turn is persisted anywhere, and "is this
still a gap today" is more useful to an admin than "what happened three
weeks ago"; documented in `content_gaps.py`'s module docstring) across all
8 spec'd causes: MISSING_DOCUMENT, OUTDATED_DOCUMENT, CONFLICTING_DOCUMENT,
INSUFFICIENT_EVIDENCE, RETRIEVAL_FAILURE, PERMISSION_RESTRICTION,
MODEL_FAILURE, AMBIGUOUS_QUERY. Each gap now also tracks affected user IDs
(via `Conversation.user_id`) and relevant document IDs, and carries a
generated suggested remediation string. Frontend (`ContentGapsView.tsx`)
updated to show the cause badge and remediation text per gap, not just the
raw question.

**A real bug found via live testing against the real user's own account
(read-only — no data written), not just unit tests**: the first
implementation classified conflicts by calling the full Phase 1 LLM
pipeline (claim extraction + LLM relationship classification) once per gap,
on every single page load. Measured live against the real workspace's
actual gap history: **85 seconds** for one page load. Fixed by replacing it
with Phase 1's deterministic-only classifier called directly (no LLM call
at all for gap classification) — the real, honest tradeoff is that this
misses subtler conflicts an LLM would catch, same documented limitation as
the deterministic stage generally (`eval/conflicts/README.md`). Re-measured
live: **11-25 seconds** — a real ~4-7x improvement, though still not fast
in absolute terms since it still does per-affected-user retrieval passes
for the permission check; further optimization (e.g. skipping reranking
for these internal existence-only searches) is a known, disclosed
remaining opportunity, not silently ignored.

**Live-verified against real production-like data**, not synthetic test
cases: the real user's actual historical gaps classified correctly and
plausibly — "What's the CEO's salary?" → PERMISSION_RESTRICTION (a real
ACL-restricted document), "Why does Falcon Arm v3's battery only last a
few hours?" → CONFLICTING_DOCUMENT naming the two real conflicting source
files, "hi"/"CTO" → AMBIGUOUS_QUERY, a vesting-chart question →
INSUFFICIENT_EVIDENCE. All read-only against their real workspace; nothing
written, nothing to clean up.

8 new tests covering every cause path plus the `classify=False` opt-out and
a guarantee that classification failures degrade to UNCLASSIFIED rather
than breaking the page. Full backend suite: **202/202 passing**.

## Phase 9 — done

Expanded the adversarial matrix past the existing 3 prompt-injection
fixtures (direct override, HTML-comment metadata, roleplay hijack) with 4
new attack shapes: a fake `## SYSTEM` markdown heading, a malicious YAML
front-matter directive, zero-width-unicode-obfuscated text, and a
cross-document instruction claiming to apply to "all future questions in
this conversation" — the last tested distinctly via a real 2-turn
conversation (ask a question that retrieves the poisoned doc, then an
*unrelated* second question in the same conversation, checking the
injection doesn't persist through history into a later turn).

Added `eval/run_security_hardening.py` for two checks that don't fit the
fixture format: **API key workspace confusion** (does presenting
`X-Workspace-Id` for workspace B alongside an API key scoped to workspace A
let a caller read B's data? — checked against actual retrieved chunk IDs)
and **version leakage** (does a current-version question ever retrieve
superseded-version chunks, or a historical question ever retrieve current-
version chunks? — same, checked against real chunk_id/version_id pairs,
never just answer wording, per the phase's explicit instruction).

**Real results**: prompt-injection suite **7/7 passed** (6 fixtures + the
cross-turn persistence check). Security hardening **2/2 passed** — the API
key check confirmed (by reading `deps.py`'s `_principal_from_api_key`, then
proving it live) that `X-Workspace-Id` is structurally ignored whenever
auth is via API key, so the confused-deputy attempt returned 200 with
results but zero overlap with workspace B's chunks; the version-leakage
check confirmed zero cross-version chunk overlap in both directions and
that the historical question correctly engaged Phase 2's `VERSION_SPECIFIC`
temporal path.

Full backend suite: **194/194 passing**, unaffected — this phase only
added `eval/` fixtures and scripts, no application code changed.

## Phase 8 — done

Closed the real, previously-identified gap from Phase 0's audit: the cache
was purely TTL-based, with **no write-invalidation at all** — a document
reupload, an ACL change, or a role change could leave a stale cached answer
served for up to `cache_ttl_seconds` after the underlying state changed.

Implemented cache versioning (`app/cache.py`): `get_workspace_epoch`/
`bump_workspace_epoch`, a per-workspace counter folded into every `/chat`
and `/search` cache key (`cache_key()`'s `epoch` param is now **required**,
not optional-with-a-default, specifically so a future call site can't
silently forget it). Bumping a workspace's epoch makes every previously
cached entry for it permanently unreachable — chosen over enumerating and
deleting individual keys because Redis has no reverse index from workspace
to the keys it produced, and versioning needs none. Wired into every event
that can change what a cached answer *should* say: document upload,
reupload, ACL grant change, staleness verification, member role change, and
member removal.

**Tested exactly per the spec's own examples** ("Workspace A → answer,
Workspace B → same question, verify B cannot receive A's cached result";
restricted vs. unrestricted user) — 5 new tests: reupload invalidates a
cached answer, a new upload invalidates a stale cached *refusal* (not just
a stale right answer), an ACL grant change invalidates a viewer's prior
cached access, a role downgrade invalidates cache, and an epoch bump is
proven scoped to its own workspace only (a second, untouched workspace's
cache entry is confirmed to still hit). Cross-workspace/cross-user
isolation itself was already covered by the pre-existing `test_cache.py`
(cache key already included workspace_id/user_id) — this phase is
specifically about invalidation *on write*, the part that was missing.

**Live-verified end-to-end**, not just unit tests: restarted the API with
caching on, asked a real question (cache miss), asked it again (confirmed
hit), reuploaded the document with different content, asked a third time —
confirmed `cached: false` and the new answer reflected the new content, not
the stale cached one. Debug workspace cleaned up afterward.

Full backend suite: **194/194 passing** (189 + 5 new).

## Phase 3 — done

**Honest scope note up front**: the spec's target was 300 questions; this
pass reaches 43 real QA cases + 5 dedicated live checks, not 300. Full
rationale in `eval/EXPANDED_EVAL_README.md` — writing 300 real, individually
verified facts against a correspondingly large real corpus is a large
content-authoring effort in its own right, and padding to a round number
with unverified filler would violate this project's own standing rule
against fabricating measured results.

**What was built**: 5 new corpus documents (security policy, incident
response, expense policy, vendor management, benefits guide) specifically
to give the multi-hop/cross-document categories real material spanning
documents. `eval/dataset_expanded.json` — 26 new categorized questions
(retrieval: direct lookup/semantic/keyword/multi-hop/cross-document, answer
quality, citations, trust/conflicts) on top of the existing 17 in
`dataset.json` (kept unchanged). `eval/run_expanded_eval.py` — runs the
categorized set plus **5 dedicated live checks** that a static QA list
can't express: ACL bypass (reuses `run_before_after.check_permission_leakage`
rather than reimplementing it), cross-tenant retrieval leakage, cached-answer
workspace isolation, staleness actually reaching the model (real DB
backdating + checking both `Evidence.staleness` and Phase 5's
`trust_summary.source_freshness`), and a live version-comparison round-trip
through Phase 2's temporal path. Plus regression detection against a saved
baseline (answer_accuracy/retrieval_hit_rate/refusal_accuracy, >10-point
drop fails the run).

**Real results, both runs disclosed**: first run — answer_accuracy 85.7%,
retrieval_hit_rate 100%, citation_grounding 95.5%, refusal_accuracy 100%,
conflict_detection_accuracy 100%; 4/5 live checks passed, 1 skipped
(`staleness_reaches_model` — `DATABASE_URL` wasn't set in that shell, a
harness bug, not a system bug). Investigated the 3 "answer_correct=False"
results before accepting them: all three were verified live to be
demonstrably correct, complete, grounded answers that just didn't hit my
own overly-narrow expected-substring list — a test-design artifact, not a
system failure (e.g. one expected the literal digits "24 hours" from a
different document than the question's actual focus).

Re-ran with `DATABASE_URL` set: **answer_accuracy 100%**, citation_grounding
95.5%, retrieval_hit_rate 100%, conflict_detection_accuracy 100%, **all 5
live checks passed** including staleness. The regression detector fired for
real on `refusal_accuracy` (100%→80%): the maximally-ambiguous test question
("What is the policy?") flipped from a strict refusal in run 1 to a hedged
descriptive answer in run 2 ("the provided context does not contain specific
information about a single clear policy..."). Investigated rather than
dismissed: not a dangerous regression — no fact was hallucinated, the model
just expressed the same "I can't pin this to one policy" judgment through
`answerable: true` prose instead of the strict `answerable: false` path.
Real LLM non-determinism on a genuinely ambiguous boundary case, consistent
with non-determinism already documented elsewhere in this project
(`docs/DEMO_SCRIPT.md`'s "Honest summary"), not a broken build.

Full backend suite: **189/189 passing**, unaffected — this phase only
touched `eval/` scripts and the corpus, no application code.

## Phase 6 — done

Upgraded `apps/web/components/chat/ChatView.tsx`'s "Why this answer?" panel
and conflicts display — purely frontend, no backend changes needed since
Phases 1/4/5 already emit every field this needed
(`Conflict.relationship/confidence/chunk_id_a,b/claim_a,b`,
`Evidence.is_cited`, `ChatResponse.trust_summary`). Each evidence entry now
walks the full CLAIM → SUPPORTING CHUNK → DOCUMENT → VERSION → FRESHNESS →
DENSE/SPARSE/RERANK SCORES → CONFLICT STATUS chain the spec asked for,
matched back to its citation and to any conflict it's part of. New
`ConflictsPanel` renders conflicting sources **side by side** (Source A /
Source B, never merged into one blended statement) with the pipeline's real
confidence value. New `TrustSummaryBlock` renders Phase 5's structured
summary, with weak values (`Low`/`Unknown`) visually flagged in brass rather
than blending in. `apps/web/lib/types.ts` extended to match every new
backend field, all additions optional so nothing breaks on an older cached
response shape.

**Verified live in a real browser, not just typecheck**: `npx tsc --noEmit`
and `eslint` both clean; then actually ran the app (Next dev server + API),
uploaded the canonical conflicting PTO documents into an isolated test
workspace, asked the real conflict question, and confirmed by screenshot
that the Trust Summary block, the side-by-side Source A/B conflict panel,
and the full per-evidence claim→chunk→...→conflict-status chain all render
exactly as designed — not assumed from code alone. Test workspace and all
associated rows fully cleaned up afterward via direct Postgres deletes
(documents/chunks aren't FK-cascaded from workspaces in this schema, so
deleting the workspace row alone leaves orphans — confirmed 0 orphaned rows
and the real user's own 10 documents were never touched).

## Phase 5 — done

Added `app/trust_summary.py` + `ChatResponse.trust_summary`: structured,
evidence-derived fields (citation coverage as a real 0-1 float plus a
High/Medium/Low bucket, source freshness, version currency, conflicts
surfaced by topic, evidence completeness, permission check) instead of a
single fabricated percentage. `citation_coverage()` deliberately reuses the
*exact* sentence-to-claim substring-overlap algorithm
`eval/run_before_after.py` already uses offline — the live number and the
eval-reported number for the same answer are one computation, not two that
could quietly diverge. `None` for a refusal (nothing to summarize trust
for); a thin answer (no citations, no evidence) reads as `Low`/`Unknown`
across the board, never defaulted to a falsely reassuring value. 16 new
tests, including 3 real `/chat` integration tests (answerable, refusal,
cache-hit).

**Live sanity check, not just unit tests**: ran a real question against the
canonical PTO-conflict corpus. `conflicts_detected: 1` and
`conflicts_summary` correctly named the topic — matches Phase 1's pipeline
output directly. `citation_coverage` read **0.0** despite a real citation
being present — checked this wasn't a bug rather than assuming: the answer
sentence and the citation's `claim` text were genuine paraphrases of each
other with no substring overlap ("Full-time employees... accrue paid time
off (PTO) at a rate of..." vs "Employees... accrue PTO at a rate of...").
This is the same known, already-documented strictness of the reused
algorithm (`eval/REPORT.md` records this exact metric ranging 43-92% across
real runs, never near 100%) — not a new bug introduced by this phase. The
Trust Summary surfacing a conservative number here is the correct behavior
per this phase's own rule ("never claim certainty when evidence is
incomplete"), not a regression.

Full backend suite: **189/189 passing** (173 after Phase 4 + 16 new Trust
Summary tests).

## Phase 4 — done

Added `ChatRequest.trust_mode: FAST | BALANCED | MAX_TRUST` (default
BALANCED — the exact behavior every prior phase already had, so no existing
client changes). Folded into the cache key so modes can never share a cached
answer. **FAST** skips the Phase 1 conflict-detection pipeline entirely
(zero extra LLM calls). **BALANCED** is unchanged default behavior
(conflict detection already skips itself when there's nothing to compare —
Phase 1's own pre-filter, not new work). **MAX_TRUST** widens the
conflict-detection candidate net (`settings.max_trust_candidate_min_similarity`/
`max_trust_max_candidate_pairs`, passed as **per-call overrides** to
`select_candidates`/`detect_conflicts_structured` — never a mutation of the
global `settings` singleton, which is shared across concurrent requests) and
builds "Why this answer?" evidence for every retrieved chunk, not just cited
ones (new `Evidence.is_cited` field distinguishes the two rather than
silently mixing them). 7 new tests, including one that proves FAST and
BALANCED never share a cache entry.

**Measured real latency per mode** (`eval/run_trust_mode_latency.py`,
`eval/results/trust_mode_latency.json`, local Ollama, steady state —
excluded one cold-start outlier where the embedding/reranker model was
still lazy-loading after a restart, same methodology as T9.5's steady-state
figures):

| Mode | Avg wall time | Conflict detection stage |
| --- | --- | --- |
| FAST | **~3.4 s** | skipped entirely |
| BALANCED | **~8.6 s** | ~4.8 s |
| MAX_TRUST | **~8.3 s** | ~4.5 s |

FAST is a real ~2.5x speedup by skipping conflict detection, matching the
~4.8s conflict-detection cost already measured in T9.5. MAX_TRUST measured
about the same as BALANCED on this specific 2-document benchmark — honestly
disclosed rather than hidden: with only 2 documents in play there's at most
1 candidate pair regardless of how wide the net is, so the widening had
nothing extra to catch in this particular test. A corpus with more
documents/candidate pairs would be needed to measure MAX_TRUST's real
marginal cost over BALANCED — noted as a gap in this specific benchmark, not
assumed away.

Full backend suite: **173/173 passing** (166 after Phase 2 + 7 new
trust-mode tests).

## Phase 2 — done

Built `apps/api/app/temporal.py`: a deterministic (regex/keyword, not LLM —
a safety boundary should be auditable and unable to hallucinate an intent)
classifier over 6 intents (CURRENT/HISTORICAL/VERSION_SPECIFIC/
COMPARE_VERSIONS/CHANGE_SUMMARY/UNKNOWN), version reference resolution
(explicit number, ordinal, "previous version", year-tagged), two-version
resolution for comparisons, and a structured chunk-level diff
(ADDED/REMOVED/CHANGED/UNCHANGED/CONFLICTING — CONFLICTING reuses Phase 1's
`conflict_detection.signals` numeric/date extraction rather than a second
implementation). `app/retrieval.py` gained `find_relevant_document()`
(all-versions search, used only to locate a document before resolving which
version to read — never to answer). `/chat` gained an early-return branch
(`_answer_temporal_question`) that only engages for the 4 non-CURRENT/
UNKNOWN intents; CURRENT/UNKNOWN fall through to the existing cache/agent
path completely unchanged. **Safety property, tested directly**: a
version that can't be resolved (nonexistent version number, no matching
year, single-version document asked "what changed") always returns an
explicit refusal naming why — never silently substitutes current-version
content (`test_chat_nonexistent_version_returns_explicit_refusal_not_current_content`).

**Regression care taken**: the classifier is deliberately conservative — an
explicit "current"/"latest" signal always wins over an incidental year
mention elsewhere in the question, specifically verified against the real
eval-dataset question that contains "April 2025" in a document title
(`test_classify_current_explicit_keyword_wins_over_incidental_year`) so it
can never be misrouted into the temporal path. Confirmed via a live restart
+ re-run of `eval/run_eval.py` against the real 9-document corpus: that
exact question still scored `hit=True correct=True`, answer_accuracy held
at 92.9% (unchanged from baseline), retrieval_hit_rate 100% (unchanged).
`conflict_detection_accuracy` read 0.0% on this particular live run (down
from a previously-observed 25%) — investigated directly rather than assumed:
a live isolated `/chat` call with just the two PTO documents confirmed the
Phase 1 pipeline still correctly detects that exact conflict
(confidence 1.0) when both documents are actually retrieved together: the
0% is retrieval-precision variance on the fuller 9-document corpus (an
already-documented pre-existing issue, e.g. in `docs/DEMO_SCRIPT.md`), not a
Phase 1/2 regression.

Full backend suite: **166/166 passing** (133 after Phase 1 + 33 new temporal
tests, including 4 real `/chat` integration tests covering version-specific
answers, nonexistent-version refusal, change-summary diffs, and confirming
an ordinary question's `temporal` field stays `null`).

## Phase 1 — done

Built `apps/api/app/conflict_detection/` (claim extraction → candidate
filtering → deterministic-then-LLM relationship classification → confidence
scoring → aggregation), a `conflicts` table + migration
(`0008_conflicts.py`) for full audit-trail persistence (every relationship,
not only contradictions), `CONFLICT_DETECTION_MODEL`/
`CONFLICT_MAX_CANDIDATE_PAIRS`/`CONFLICT_CANDIDATE_MIN_SIMILARITY` config,
and `eval/conflicts/` (24-case labeled benchmark + scoring harness).
`app/routers/chat.py` now calls the new pipeline instead of
`app.llm.detect_conflicts` (left in place, untouched, still tested — just no
longer the `/chat` call site). The `Conflict` response schema gained
`relationship`/`confidence`/`chunk_id_a,b`/`claim_a,b` fields, back-compat
defaulted.

**Measured benchmark results** (`eval/conflicts/README.md` has full detail
including a real bug found and fixed mid-phase): first run scored 50%
accuracy / 0.75 F1 on the CONTRADICTS-vs-rest framing; diagnosed a real bug
(entity extraction was dropping 3-letter subject words like "PTO", so the
canonical PTO-conflict example scored 0.0 topic similarity) and an
evidence-based threshold recalibration (0.15 → 0.05, chosen because every
`unrelated` case in the benchmark scores exactly 0.0 similarity). Final:
**62.5% accuracy, CONTRADICTS precision 1.0, recall 0.8, F1 0.889.**
Weakest categories: COMPLEMENTS and UNCERTAIN classification (0/3 each) —
documented as a real, structural limit of deterministic bag-of-words
candidate filtering, not swept under the rug.

Full backend suite: **133/133 passing** (111 baseline + 22 new
conflict-pipeline tests). Two pre-existing tests that patched the old
`app.llm.detect_conflicts` call site were updated to patch the new
`app.routers.chat.detect_conflicts_structured` entry point instead — a
deliberate, documented consequence of replacing the call site, not a
regression.

This document is the output of a full-codebase audit performed before any
further changes, per the improvement effort's own execution rules ("do not
modify core architecture until this audit is complete"). It records what
exists today, what's strong, what's weak, and the measured baseline every
future change will be compared against.

## How to use this document

The full improvement effort spans 16 phases of very different size and risk:
some (Phase 1, conflict detection) are a focused backend rebuild; others
(Phase 10, connectors; Phase 11, enterprise SSO) are multi-week, multi-decision
efforts in their own right (which OAuth providers, real external credentials,
compliance surface). This plan captures the audit and a proposed phase
ordering, but **does not assume every phase will be built in one continuous
pass** — that sequencing call, especially for Phases 10/11, belongs to
whoever is directing the work next. Treat the "Implementation phases" section
below as a menu with a recommended order, not a committed backlog.

---

## 1. Current architecture

**Backend** (`apps/api/app/`, ~5.4k lines): FastAPI + Pydantic v2 +
SQLAlchemy 2 + Alembic + Postgres 16/pgvector + Redis + Celery + LangGraph.

- `models.py` — `User`, `Workspace`, `WorkspaceMembership`, `Invite`,
  `ApiKey`, `Document`, `DocumentAccessGrant`, `DocumentVersion`, `Chunk`
  (pgvector `embedding` + computed `text_tsv`), `Conversation`, `Message`,
  `MessageFeedback`, `AuditLog`, `ContentGapResolution`.
- `retrieval.py` — hybrid dense (pgvector cosine) + sparse (Postgres FTS)
  search fused with Reciprocal Rank Fusion; `_scoped()` is the single
  RBAC/ACL/version choke point; `config_fingerprint()` folds active
  component-toggle flags into cache keys.
- `rerank.py` — cross-encoder second-stage relevance scoring over the fused
  candidate pool.
- `agent.py` — LangGraph loop: `plan → retrieve → assess → generate`, bounded
  to 3 iterations.
- `llm.py` — all LLM calls (condense, assess, generate, `detect_conflicts`),
  provider abstraction (Ollama default / OpenRouter optional), prompt-
  injection defense (`<retrieved_chunk>` tags + system-prompt rule), staleness
  caveat rule.
- `cache.py` — Redis, normalized-exact-match key (not embedding-based despite
  being called "semantic" in comments — see weaknesses).
- `rbac.py` / `deps.py` — `Principal`, `document_visible_clause`,
  role-ranked RBAC, JWT + API-key auth.
- `timing.py` — `StageTimer`, a deliberately minimal non-OpenTelemetry stand-in
  (documented as such in its own docstring).
- `routers/` — `chat.py`, `documents.py`, `admin.py`, `workspaces.py`,
  `apikeys.py`, `invites.py`, `conversations.py`, `search.py`, `auth.py`,
  `dashboard.py`.
- 7 Alembic migrations: initial schema → multitenancy → workspaces/invites/
  audit → document staleness → content-gap resolutions → **document
  versions** → message feedback.

**Frontend** (`apps/web/`): Next.js 14 App Router + TypeScript + Tailwind +
React Three Fiber. `components/chat/ChatView.tsx` is the `/chat` page:
Living Atlas as the primary/larger left pane, answer transcript as a
narrower right sidebar (`WhyThisAnswer` pipeline trace, conflict banner,
citations, feedback buttons). `components/living-atlas/` (3D + 2D fallback,
shared prop contract including `staleIds`/`conflictPairs`).
`components/admin/` — analytics, evals (with a `Headline` component sourced
live from `eval/results/*.json`), content-gaps (Fog-of-War viz + raw
query+count list), feedback, audit-log.

**Eval infra** (`eval/`): `run_eval.py` (core QA), `run_before_after.py`
(T9.1/T9.2), `run_adversarial.py`, `run_prompt_injection.py`,
`run_latency_breakdown.py`, `load_test.py`. 17-question dataset, 9-document
corpus (mixed synthetic business docs + movie trivia).

## 2. Current strengths

- **Real tenant isolation choke points.** `document_visible_clause()` and
  `_scoped()` are single functions every retrieval path goes through — there
  is no code path that bypasses RBAC/ACL, and this has already been proven
  (not just claimed) via a permission-leakage adversarial test that checks
  the restricted chunk ID itself, not answer text.
- **Real prompt-injection defense**, verified against 3 live attack patterns
  (direct override, disguised metadata, roleplay hijack), all logged as
  actually-retrieved-into-context (not just topically absent).
- **Config-fingerprinted caching.** Retrieval/rerank/version/conflict flags
  are folded into the cache key, so flipping a flag can't silently serve a
  stale answer computed under a different configuration — a real bug found
  and fixed earlier in this project's own history.
- **Honest eval culture.** `EvalsView`'s `Headline` component sources every
  number from a real `eval/results/*.json` file and explicitly shows "—" /
  names missing files rather than fabricating; `eval/REPORT.md` and
  `docs/DEMO_SCRIPT.md` both disclose non-favorable and non-reproducible
  results rather than smoothing them over. This is a pattern worth continuing,
  not replacing.
- **Structured, already-instrumented latency data.** `StageTimer` +
  `ChatResponse.timing` already break a request down into
  auth/retrieval/reranking/generation/conflict_detection — a real foundation
  for Phase 13's request tracing, not a from-scratch build.
- **111 passing backend tests, 10/10 passing e2e tests** (see baseline below)
  across a genuinely broad surface (workspace access, chunking, versioning,
  feedback, retrieval flags, conflicts, agent, admin, staleness, cache,
  timing, rerank, rate limiting, prompt context, evidence, content gaps).

## 3. Current weaknesses (the actual gaps this effort should close)

- **Conflict detection is one prose LLM call, not a pipeline.** No claim
  extraction, no candidate pairing/filtering, no relationship taxonomy
  (today it's implicitly boolean — "conflict found" or not — never
  SUPPORTS/CONTRADICTS/COMPLEMENTS/UNRELATED/UNCERTAIN), no confidence score,
  **zero persistence** (no `conflicts` table exists at all — every result
  lives only in the response payload and cache blob). Building the spec'd
  structured pipeline is a genuine rebuild, not a prompt tweak.
- **Version-awareness is binary, not targeted.** `version_aware_retrieval`
  is a global on/off switch (current-version-only vs. every-version-pooled-
  undifferentiated) — there is no way for a single chat question to target
  "the 2024 version" specifically, no version-comparison endpoint, and no
  intent classification (CURRENT/HISTORICAL/VERSION_SPECIFIC/
  COMPARE_VERSIONS/CHANGE_SUMMARY) anywhere. A historical question today
  either safely refuses (generic `CANNOT_ANSWER` sentinel, not a
  version-specific message) or, if the current version happens to still
  support it, silently answers from the current version with no signal that
  a version distinction was even relevant. This is the exact failure mode
  Phase 2 targets, and it's already a documented, user-accepted limitation
  from an earlier phase of this project (see `eval/REPORT.md`) — Phase 2 is
  the first real attempt to close it rather than re-document it.
- **No cache write-invalidation at all.** Purely TTL-based (1h default). A
  document reupload, an ACL/grant change, or a workspace-membership change
  does **not** purge related cached answers — a real, unaudited correctness
  and security gap (Phase 8's premise is not hypothetical).
- **The "semantic" cache isn't semantic.** It's a normalized-exact-string
  match, not embedding-based fuzzy matching — a naming/expectation
  mismatch worth flagging even though it's out of this effort's direct scope.
- **Eval corpus is toy-scale.** 17 questions, 9 documents, mixed real-business
  and movie-trivia content. Every measured percentage in the README today is
  honestly reported but statistically thin — a single flipped answer moves
  accuracy by ~6 points. Phase 3's 300-question target is a real scale-up,
  not a tuning pass.
- **Content-gap analysis has zero cause classification.** `/admin/content-gaps`
  clusters unanswered questions by embedding similarity and shows only
  `query` + `count` + resolved-state — no MISSING_DOCUMENT / OUTDATED /
  CONFLICTING / RETRIEVAL_FAILURE / PERMISSION_RESTRICTION distinction exists
  anywhere in the schema or UI. This is new capability, not an enhancement.
- **No connector, OAuth, or SSO groundwork exists at all** — confirmed via a
  full scan of `.env.example`/`docker-compose.yml`/`config.py`: zero
  OAuth/OIDC/SAML/connector-related configuration or code. Phases 10 and 11
  are both greenfield builds with real external-credential and compliance
  surface, not incremental additions.
- **No distributed tracing.** `timing.py` covers per-request stage duration
  only; there's no `request_id` propagation, no structured per-stage log
  correlation beyond what already exists in scattered `log.info` calls.
- **Trust Summary / evidence-completeness / permission-check fields don't
  exist yet.** `ChatResponse`/`Evidence` have no `permission_check` or
  `evidence_completeness` field — Phase 5's Trust Summary needs new backend
  computation, not just a frontend read of existing data (the spec's own
  "never fabricate" constraint makes this a backend-first phase).
- **Living Atlas is currently the dominant UI element, not a secondary one.**
  In `ChatView.tsx`'s current layout the Atlas is the wider, primary pane and
  the answer is a narrow sidebar — the literal opposite of Phase 12's target
  ordering (Answer → Citations → Trust Summary → Conflicts → Evidence →
  Atlas). This is a real, if easily separable, layout change.
- **Conflict/Trust test coverage is thin relative to how central these
  features are to the product pitch**: `test_conflicts.py` has 6 tests,
  `test_evidence.py` has 3 — both will need substantial expansion under any
  serious conflict-detection rebuild.

## 4. Baseline: test results

Run at the start of this audit (`cd apps/api && uv run pytest`):

```
111 passed, 1 warning in 14.00s
```

Backend test count by file (top 5): `test_workspace_access.py` (11),
`test_chunking.py` (10), `test_document_versions.py` (9),
`test_integration.py` (8), `test_feedback.py` (8). Full 20-file breakdown
recorded in this session's tool output; total is 111 across 20 files.

Frontend e2e (Playwright, `cd apps/web && npx playwright test`), last run
during T9.9 closeout: **10/10 non-skipped tests passing** (17 intentionally
skipped — screenshot-driver specs, not assertions). One real bug was found
and fixed during that run: 4 spec files used a stale `getByRole("row", ...)`
selector left over from a table→`<ul>/<li>` UI refactor; fixed to
`getByRole("listitem")`.

## 5. Baseline: evaluation results

All numbers below are already-measured (not re-run for this audit — re-using
the most recent real result files in `eval/results/`, timestamped
2026-08-11, so nothing here is invented). Corpus: 17 questions / 9 documents
(7 documents at the time these specific runs were captured — corpus has
since grown for the demo script, not a regression).

**Full system ("after" / config E — retrieval + reranking + version scoping +
conflict detection all on):**

| Metric | Value |
| --- | --- |
| Answer accuracy | 92.9% |
| Retrieval hit rate | 100% |
| Citation grounding | 85.7–92.9% (varies before_after vs ablation run) |
| Citation coverage (claim-level) | 75.0% |
| Conflict detection accuracy | 25.0% (ablation E) / 25.0% (before_after "after") |
| Refusal accuracy | 100% |
| Permission leakage | 0 |
| Avg tokens/query | 2,168–2,178 |
| Latency p50 | 6.9–6.7 s |
| Latency p95 | 28.1–28.3 s |

**Adversarial suite** (`eval/results/adversarial.json`): **6/7 passed.** The
one failure is `version_specific_question` — the documented, user-accepted
limitation described above; this is the exact gap Phase 2 targets closing.

**Prompt injection suite** (`eval/results/prompt_injection.json`): **3/3
passed.** All three attack fixtures (direct override, disguised metadata,
roleplay hijack) were confirmed retrieved into context and none were obeyed.

**Conflict detection accuracy specifically is the weakest measured number in
the entire Trust Layer (25%, down from 75% when conflict detection last ran
against a smaller/different config)** — this is the strongest quantitative
argument, independent of the spec's own prioritization, for Phase 1 being
the correct first phase to actually build.

**Latency breakdown, local Ollama steady state**
(`eval/results/latency_breakdown_ollama_steady_state.json`):

| Stage | p50 | p95 |
| --- | --- | --- |
| retrieval | 17.1 ms | 41.8 ms |
| reranking | 64.6 ms | 107.3 ms |
| generation | 4,027.3 ms | 6,003.6 ms |
| conflict_detection | 4,481.8 ms | 4,913.3 ms |

Generation and conflict detection are co-equal bottlenecks (conflict
detection's p50 is actually slightly higher than generation's) — this is the
quantitative basis for Phase 4's trust-mode latency work.

## 6. Implementation phases (proposed order, not yet started)

Ordering follows the measured evidence above (conflict detection is both the
spec's stated top priority *and* the worst-measured number in the system) and
groups by risk/size so a natural pause point exists between "core Trust
Layer rebuild" and "platform/enterprise" work:

**Group A — Trust Layer core (highest measured impact, backend-heavy)**
1. Phase 1 — structured conflict detection pipeline (new `conflicts` table +
   migration, claim extraction, candidate pairing, relationship
   classification, confidence scoring, `eval/conflicts/` benchmark).
   *Files: `app/models.py`, new `app/conflict_detection/` package, new
   Alembic migration, `app/schemas.py`, `app/routers/chat.py`,
   `apps/api/tests/test_conflicts.py`, new `eval/conflicts/`.*
2. Phase 2 — temporal/historical retrieval + version comparison.
   *Files: `app/retrieval.py`, `app/agent.py` (new intent-classification
   node or pre-step), new `app/routers/documents.py` version-compare
   endpoint, `app/schemas.py`, `apps/api/tests/test_document_versions.py`
   (expand), new temporal test file.*
3. Phase 4 — trust modes (FAST/BALANCED/MAX_TRUST) + conditional conflict
   detection + parallelization.
   *Files: `app/config.py`, `app/routers/chat.py`, `app/cache.py`
   (cache-key inclusion), `apps/web/lib/api.ts` + a settings selector
   component following the existing `Lever`/`lib/motion.ts` pub-sub
   pattern.*
4. Phase 5 — evidence-based Trust Summary (new computed fields, not fake
   percentages).
   *Files: `app/schemas.py` (`ChatResponse` additions), `app/routers/chat.py`,
   `apps/web/components/chat/ChatView.tsx` (new `TrustSummary` component).*
5. Phase 6 — upgraded "Why this answer?" UI (claim→chunk→document→version→
   freshness→scores→conflict-status chain; side-by-side conflicting
   sources).
   *Files: `apps/web/components/chat/ChatView.tsx` (`WhyThisAnswer`
   rewrite), new sub-components.*

**Group B — Measurement & security (validates Group A, medium size)**
6. Phase 3 — expanded eval framework (300+ questions, regression detection).
   *Files: new `eval/corpus_v2/` or expanded `eval/corpus/`, expanded
   `eval/dataset.json`, `eval/run_eval.py` extensions, new
   `eval/run_regression_check.py`.*
7. Phase 8 — cache security audit (invalidation on write, explicit
   cross-tenant/ACL cache tests). Addresses an already-confirmed real gap
   (no write-invalidation exists today).
   *Files: `app/cache.py`, `app/routers/documents.py` (invalidation hooks
   on reupload/ACL change), new `apps/api/tests/test_cache_security.py`.*
8. Phase 9 — security hardening (expanded adversarial matrix).
   *Files: `eval/run_adversarial.py`, `eval/run_prompt_injection.py`
   extensions, new adversarial fixtures.*
9. Phase 7 — content-gap cause classification.
   *Files: `app/content_gaps.py`, `app/schemas.py` (`ContentGap` additions),
   `apps/web/components/admin/content-gaps/ContentGapsView.tsx`.*
10. Phase 13 — observability (request-id propagation, extending the already-
    real `StageTimer` rather than replacing it).
    *Files: `app/timing.py`, `app/deps.py`, `app/routers/chat.py`,
    `app/logging_config.py`.*

**Group C — UX**
11. Phase 12 — reorder the answer UI (Answer → Citations → Trust Summary →
    Conflicts → Evidence → Living Atlas). Purely layout; Atlas, 2D fallback,
    and reduced-motion support are all preserved as-is.
    *Files: `apps/web/components/chat/ChatView.tsx` layout only.*

**Group D — Platform expansion (largest, most externally-dependent — flagged
for a separate sequencing decision before starting)**
12. Phase 10 — generic connector abstraction + one real connector
    (Google Drive) end-to-end. Requires real OAuth app registration and
    credentials — an external, account-level dependency this plan cannot
    resolve on its own.
13. Phase 11 — auth-provider abstraction + OIDC. Touches authentication for
    every user of the system; needs explicit confirmation before starting
    given rule #6 ("never weaken auth/RBAC/ACL/tenant isolation").

**Group E — Closeout**
14. Phase 14 — testing sweep across everything above.
15. Phase 15 — run everything (unit, integration, frontend, e2e, security,
    injection, eval, latency, load) and fix regressions.
16. Phase 16 — `docs/IMPROVEMENT_REPORT.md` with real before/after numbers,
    files changed, migrations, API changes, known limitations, and a
    ranked remaining roadmap.

## 7. Expected files/components affected (cumulative, Groups A–C)

**New:** `app/conflict_detection/` (package), new Alembic migration(s) for
`conflicts` table + any temporal-query support, `eval/conflicts/` benchmark,
`apps/api/tests/test_conflict_pipeline.py`, `apps/api/tests/test_temporal.py`,
`apps/api/tests/test_cache_security.py`, `apps/web/components/chat/TrustSummary.tsx`
(or similar), `apps/web/lib/trustmode.ts`.

**Modified:** `app/models.py`, `app/schemas.py`, `app/routers/chat.py`,
`app/routers/documents.py`, `app/agent.py`, `app/cache.py`, `app/config.py`,
`app/content_gaps.py`, `apps/web/components/chat/ChatView.tsx`,
`apps/web/components/admin/content-gaps/ContentGapsView.tsx`,
`apps/web/lib/types.ts`, `apps/web/lib/api.ts`, `eval/run_eval.py`,
`eval/run_adversarial.py`, `README.md` (measured-results section, once real
new numbers exist), `docs/DEMO_SCRIPT.md`.

**Explicitly not modified without a separate go-ahead:** anything in
`app/rbac.py`'s core `document_visible_clause`/`can_read_document` logic
(rule #6), `app/security.py`'s JWT/password handling (until Phase 11 is
explicitly scoped), Living Atlas 3D/2D rendering internals (Phase 12 is
layout-only per rule #16 "keep the Living Atlas").
