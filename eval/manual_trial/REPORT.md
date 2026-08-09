# AtlasKB — Northwind Robotics Trial Evaluation

Harness: `eval/manual_trial/` (`questions.json`, `harness.py`, `config.json`).
Corpus: the 6 Northwind PDFs in *joelrtharakan@gmail.com's workspace*
(`f3d30555-…`). Auth: access-token JWTs minted with the repo `JWT_SECRET`;
workspace/role resolved server-side from membership. Roles used: **admin**
(owner), **editor**, **viewer** (`trial-viewer@northwind.test`, created for the trial).

Verdicts: **pass / partial / fail / manual** (nuance flagged for human review) /
**blocked** (LLM provider 429/502 — not a quality failure).

---

## Summary table (pass rate by root-cause layer)

Verdict counts (per `harness.py`, judged item granularity, N=57):

| Layer | Before (OpenRouter) | After (Ollama `qwen3:8b`) | Notes |
|---|---|---|---|
| Retrieval | 17/19 (2 blocked) | **19/19** | Hybrid RRF handles tokens, semantics, typos, and absent-query low-scoring. No change needed. |
| Access control | 0/6 (4 blocked) | **6/6** | Restricted doc leaked to non-admins; fixed with an admin-only grant. Search leak fix is LLM-independent. |
| Agent / orchestration | 13/17 (1 blocked) | **14/17** (+3 manual) | Conversation memory now passed to agent (A2 `fail→pass`, LLM-independent of provider). |
| Generation / grounding | 1/1 (false-premise declined) | **1/1** | Strict grounding refuses; prompt also *corrects* the premise. |
| Ingestion (tables/charts) | 0/10 (10 blocked) | **10/10** | `pypdf` flattens tables to inline text but preserves values in order; chart-derived facts declined, not fabricated. |
| Chunking | 0/4 (4 blocked) | **4/4** | Split access-matrix row still answerable. |
| **Overall** | **31 pass / 3 fail / 2 manual / 21 blocked** | **54 pass / 0 fail / 3 manual / 0 blocked** | Full LLM-dependent suite completed locally with **zero quota blocks**. |

> **The full chat + PDF evaluation now completes end-to-end locally** against a
> **local Ollama daemon running `qwen3:8b`** — **0 blocked** (previously 21 were
> blocked by the OpenRouter 50-req/day cap). Numbers above are the actual harness
> verdicts from `results/after.json` (full per-question diff in
> `AFTER_COMPARISON.md`). See [comparability](#before-vs-after-comparability): the
> BEFORE column is the OpenRouter partial run, so most `blocked→pass` deltas
> reflect **quota removal**, not code fixes; the genuinely LLM-independent code
> fixes are the ACL search leak (`s_acl_*` `fail→pass`) and conversation memory
> (`A2` `fail→pass`).

---

## What was tested and found

### Retrieval — strong (17/17)
- Basic relevance, exact tokens (`ISO/TS 15066`, `$8,600`, `12 kg`,
  `northwind/tap/nw-cli`), semantic/synonym (`time off balance`→PTO, `robot arm
  stops itself`→collision detection, `who can see confidential data`→data
  classification), and typos (`servo moter`, `saftey`) all land the correct
  document in the top 1–3.
- Absent queries (`battery life`, `customer refund policy`) return only
  low-similarity chunks (max dense ≈ 0.16–0.17, well under the 0.55 bar) — no
  forced high-confidence match.
- Multi-doc queries (`access`, `device-gateway`) return ≥2 distinct sources.

### Access control — the restricted doc was **not actually restricted** (fixed)
- `06_executive_compensation_plan_RESTRICTED.pdf` had **zero access grants**.
  Under the ACL model (no grant ⇒ visible to all members), the viewer/editor
  could retrieve its salary and severance chunks. `s_acl_salary` / `s_acl_severance`
  **failed (leak)** in the before run.
- Root cause: **configuration**, not a broken mechanism — the retrieval-time ACL
  (`document_visible_clause`) works, but a grant was never created; the doc was
  "restricted" in name only.

### Agent / orchestration — conversation memory was never passed to the agent
- `run_agent(body.question, retrieve)` received only the current question. Prior
  turns were persisted to `messages` but never loaded or fed back.
- Masking effect: many follow-ups *passed anyway* because their wording carried
  enough keywords to retrieve directly (C2 "safety features", C3 "stop after a
  collision", E3 "…about PTO…", G7 "on-call rotation length"). The clean
  demonstration of the gap is **A2 "Has that changed recently?"** — no topical
  keywords ⇒ retrieval found nothing ⇒ **not-answerable (hard fail)**. Citation
  drill-down (G6) and self-referential summary (G8) also depend on memory.

### Generation / grounding
- False premise (D1 "why does the battery only last a few hours?"): strict
  grounding already returns *not-answerable* rather than inventing a figure
  (pass). Prompt now also instructs the model to *state* the premise is
  unsupported.

---

## Fixes implemented

1. **Conversation memory in the agent** (`llm.py`, `agent.py`, `routers/chat.py`)
   - `chat.py` now loads prior turns (`_load_history`) and passes them in.
   - New `llm.condense_query(history, question)` rewrites a follow-up into a
     standalone retrieval query (resolves "it/that/the policy"); injected into the
     agent as `condense_fn` and applied on the first retrieval pass. No-op with no
     history, so single-turn behavior and existing tests are unchanged.
   - `llm.generate_answer(question, chunks, history=…)` includes prior turns so
     the model resolves references and can answer questions about the conversation
     itself (self-referential/meta), which are allowed to have no document citation.
   - **Cache-correctness fix:** the chat cache key now folds in a conversation
     digest, so the same follow-up text in different threads can't collide.
   - Verified with a new unit test (`test_condense_rewrites_first_query_from_history`)
     and the full suite (54 passed) — LLM-independent.

2. **Restrict the executive-comp document** (data/config via the real API path)
   - `PATCH /documents/{id}/access` with an **admin-only role grant**. Re-verified:
     viewer `salary bands` / `severance terms` now return **zero** restricted
     chunks (19/19 search pass).

3. **Prompt hardening** for pronoun resolution + explicit false-premise correction
   (`_SYSTEM_PROMPT`).

---

## LLM provider (OpenRouter → Ollama)

- **Provider:** local **Ollama** daemon, OpenAI-compatible API at
  `http://127.0.0.1:11434/v1` (loopback only — port 11434 is never published
  publicly, nor via nginx/Cloudflare/Docker; from a container it is reached over
  `host.docker.internal`).
- **Model:** `qwen3:8b` (Q4_K_M, 8.2B, digest `500a1f067a9f`). **Temperature:**
  `0` (unchanged from the OpenRouter config). **System/condense/assess prompts:**
  unchanged. **Response format:** `json_object`; a tolerant parser strips Qwen's
  `<think>…</think>` reasoning before JSON decoding.
- **Thinking disabled:** Qwen3 defaults to a long chain-of-thought that on an 8B
  local model exceeded the harness's 180 s client timeout for a single
  query-rewrite (observed >180 s). A leading `/no_think` system message (Qwen3's
  documented soft switch, scoped to the Ollama provider) disables it — condense
  drops from >180 s to ~14 s. Grounding is unaffected (answers stay constrained to
  retrieved context).
- **Stability:** `OLLAMA_KEEP_ALIVE=30m` pins the model resident so it is not
  evicted mid-run (an eviction/reload race caused the first run to time out).
- **Why Ollama:** the OpenRouter free tier caps at **50 requests/day**, which the
  **38 LLM-dependent questions** (21 chat + 17 pdf, multiple LLM calls each)
  exhaust mid-run (42 `/chat` calls this run alone). A local model removes the
  quota, keeps data on-device, and introduces **no paid API**.
- **Selection:** `LLM_PROVIDER=ollama` (default) or `openrouter` (kept as an
  optional fallback — no OpenRouter code was deleted). One OpenAI-compatible
  client serves both; no new dependency.
- **Eval fan-out:** `AGENT_MAX_ITERATIONS=1` (single retrieval pass, no second
  assessment LLM call) is appropriate for the 6-doc corpus and is set via the
  existing environment configuration — not hard-coded.

### BEFORE vs AFTER comparability

- The `AFTER_COMPARISON.md` table pits the **OpenRouter BEFORE** (which did *not*
  complete — 21/57 items blocked by the 429 daily cap) against the **Ollama
  AFTER**. **This comparison is confounded by the provider/quota change:** most
  `blocked→pass` deltas mean "the question could finally run at all", **not** that
  a code fix improved quality. Do **not** read the headline 31→54 as a pure
  code-fix gain.
- **What *is* attributable to the code fixes** (both LLM-independent, so provider
  cannot confound them): the ACL search leak — `s_acl_salary`/`s_acl_severance`
  `fail→pass` via `/search` (no LLM) — and conversation memory — `A2`
  ("has that changed recently?") `fail→pass`, which failed on OpenRouter too
  because history was never passed to the agent.
- A clean, non-confounded quality baseline would require a Qwen `qwen3:8b`
  BEFORE run on the **pre-fix** code. That was **not** produced here: reverting the
  conversation-memory/ACL logic is explicitly out of scope (frozen, 54/54 tests).
  The AFTER config (model/version, temperature 0, prompts, `/no_think`, retrieval,
  questions, judging) is fully recorded above so such a baseline is reproducible.

### Verification status — completed locally

- **Unit/integration tests: 54/54 pass** (LLM-independent; retrieval 5, ACL/
  workspace-access 11, agent 6, cache 4, integration 8, chunking 7, others).
- **Live Ollama eval: completed.** `harness.py --phase after` ran the full suite
  against `qwen3:8b` on a local Ollama daemon. **38 LLM-dependent questions**
  (21 chat + 17 pdf) over **42 `/chat` requests**; **0 blocked**. Per-`/chat`
  latency: median **~33 s**, max **~116 s** (under the harness's 180 s timeout);
  ~26.5 min total. Results in `results/after.json`, diff in `AFTER_COMPARISON.md`.
- **Manual (3):** self-referential/citation-drill-down items flagged for human
  confirmation (e.g. G8) — not failures.
- **Latency note:** Qwen3 thinking is disabled for these calls (leading
  `/no_think`) so a single 8B generation stays within client timeouts; the model
  is pinned resident via `OLLAMA_KEEP_ALIVE=30m`.
- **Spot checks:** basic RAG (ISO/TS 15066, cited), multi-turn + follow-up needing
  history (A2 PTO update), role-based auth, restricted-doc refusal
  (`p_leak_exists`/`p_viewer_restricted`), and semantic cache hit (`cached:true`,
  0 tokens on repeat) all verified.

## Known limitations (intentionally not hacked)

- **Chart/image-only facts (no vision/OCR).** "% vested after 2 years" lives only
  in a vesting *chart image*; the text says "4-year vesting, 1-year cliff". A real
  fix is a vision extraction step at ingest (render page → multimodal model, or a
  table/figure OCR pass) writing figure captions/derived values as chunk text.
  The harness checks the system does **not fabricate** a percentage.
- **ACL changes don't invalidate the semantic cache.** After adding the grant, the
  viewer still saw cached leaky results until the namespace was flushed (TTL 1h).
  A real fix keys cache entries on an ACL/version stamp, or invalidates a
  workspace's cache on grant changes.
- **`pypdf` flattens tables** to inline text (values preserved and ordered, so most
  table facts are answerable). `pdfplumber`/structured extraction would improve
  faithful table *reconstruction* and split-row cases (security access matrix).
- **OpenRouter free tier: 50 requests/day**, shared across all `:free` models, and
  the app surfaces the upstream 429 as a 502. This blocked the chat/PDF AFTER run
  and motivated the move to local Ollama. **The finding still stands** for the
  optional `LLM_PROVIDER=openrouter` path: an upstream 429 is still masked as a
  502 (`routers/chat.py`). Only the *unreachable-daemon* case is now mapped to a
  clear 503 ("Ollama is unavailable…") — the 429→502 masking was left unchanged.
