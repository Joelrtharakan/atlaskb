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

| Layer | Before | After | Notes |
|---|---|---|---|
| Retrieval | 17/17 | 17/17 | Hybrid RRF handles tokens, semantics, typos, and absent-query low-scoring. No change needed. |
| Access control | 0/2 search (+chat blocked) | **2/2 search** (chat pending) | Restricted doc leaked to non-admins; fixed with an admin-only grant. Verified via `/search`. |
| Agent / orchestration | 13 pass, **1 hard fail (A2)**, 2 manual, 1 blocked | pending LLM | Conversation memory not passed to agent; implemented + unit-tested. |
| Generation / grounding | 1/1 (false-premise declined) | pending LLM | Strict grounding already refuses; prompt improved to *correct* the premise. |
| Ingestion (tables) | mostly OK (blocked in before) | pending LLM | `pypdf` flattens tables to inline text but preserves values in order. |
| Ingestion (charts) | — | — | **Known limitation:** chart-image-only facts (e.g. % vested at 2 yrs) — no OCR/vision. |
| Chunking | (blocked in before) | pending LLM | One artifact: the security access-matrix "Admin" row splits across a chunk boundary. |

> The full **chat + PDF AFTER re-run was blocked on the OpenRouter free-tier daily
> cap** (50 req/day, exhausted mid-run). To remove the quota dependency entirely,
> the LLM provider has been migrated to a **local Ollama daemon running
> `qwen3:8b`** (see [LLM provider](#llm-provider-openrouter--ollama)). Retrieval
> and access-control fixes are already proven without the LLM (54/54 unit tests).
> The AFTER chat/PDF pass runs against Ollama; results are recorded only once that
> pass has actually executed locally — no numbers are carried over from OpenRouter.

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
- **Model:** `qwen3:8b`. **Temperature:** `0` (unchanged from the OpenRouter
  config). **System/condense/assess prompts:** unchanged. **Response format:**
  `json_object`; a tolerant parser strips Qwen's `<think>…</think>` reasoning
  before JSON decoding.
- **Why Ollama:** the OpenRouter free tier caps at **50 requests/day**, which the
  ~39 LLM-dependent questions (multiple LLM calls each) exhaust mid-run. A local
  model removes the quota, keeps data on-device, and introduces **no paid API**.
- **Selection:** `LLM_PROVIDER=ollama` (default) or `openrouter` (kept as an
  optional fallback — no OpenRouter code was deleted). One OpenAI-compatible
  client serves both; no new dependency.
- **Eval fan-out:** `AGENT_MAX_ITERATIONS=1` (single retrieval pass, no second
  assessment LLM call) is appropriate for the 6-doc corpus and is set via the
  existing environment configuration — not hard-coded.

### BEFORE vs AFTER comparability

- The OpenRouter BEFORE run **did not complete** the LLM-dependent questions (it
  was blocked by the 429 daily cap), so there is **no valid OpenRouter baseline**
  to compare against. Any code-fix improvement must therefore be shown with a
  **controlled BEFORE/AFTER using the same `qwen3:8b` configuration** — same
  model/version, temperature, prompts, retrieval config, questions, and judging.
- Do **not** attribute a Qwen-AFTER vs OpenRouter-BEFORE delta to the code fixes;
  the provider change alone would confound it.

### Verification status

- **Unit/integration tests: 54/54 pass** (LLM-independent; retrieval 5, ACL/
  workspace-access 11, agent 6, cache 4, integration 8, chunking 7, others).
- **Live Ollama chat/PDF/eval pass:** to be run on a host with Ollama installed
  and `qwen3:8b` pulled (Ollama was not available in the implementation
  environment). Numbers will be filled in from the actual run only — none are
  fabricated here.

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
