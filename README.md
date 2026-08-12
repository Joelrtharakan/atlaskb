# AtlasKB

**AtlasKB is a multi-tenant, agentic RAG platform that doesn't just answer
questions from your documents — it proves the answer is trustworthy.** Teams
upload documents into isolated workspaces; a LangGraph agent plans retrieval
over a hybrid (dense + full-text) index, reranks what it found with a
cross-encoder, checks whether it has enough to answer, and returns a grounded
answer where every claim links back to the exact source chunk. Beyond that
baseline RAG loop sits a **Trust Layer**: document versioning so a superseded
policy never gets cited as current, cross-document conflict detection so
contradicting sources are surfaced rather than silently blended, a staleness
signal that reaches all the way into the LLM's own prompt, a full "why this
answer?" evidence trail, and a feedback + audit log — all of it validated
adversarially and measured before/after rather than taken on faith (see
[Measured results](#measured-results)). A 3D "Living Atlas" turns each answer
into a map: the camera flies to the documents that answered you, lights a
route between them, and rings any node that's stale or in conflict.

> **Demo.** No public instance is hosted — but the clip below is a real recording,
> and the whole stack runs locally in a few minutes (see [Quickstart](#quickstart)).
> A full narrated walkthrough of every Trust Layer capability, run live and
> honestly reported, is in [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

![The Living Atlas answering a real question](docs/media/living-atlas.gif)

<sub>Ask → the retrieved document nodes light amber and draw threads to the answer point → the cited answer appears in the panel; hovering a citation highlights its node. Falls back to a 2D map under reduced-motion / low-power.</sub>

---

## What it does

**Core RAG loop**

- **Grounded Q&A with citations.** Answers are generated *only* from retrieved
  chunks; each claim maps to the chunk IDs that support it, and the agent refuses
  ("cannot answer from the available documents") rather than hallucinate.
- **Hybrid retrieval + reranking.** pgvector cosine similarity (dense) fused
  with Postgres full-text search (sparse/BM25-style) via Reciprocal Rank
  Fusion, then re-scored by a cross-encoder that reads the query and each
  chunk together — measured as the single highest-leverage addition in this
  project's own ablation study (see below).
- **Agentic retrieval loop (LangGraph).** plan → retrieve+rerank → assess
  sufficiency → optionally re-query (hard-bounded at 3 iterations) → generate.
  Re-querying is capped so cost can't run away.
- **Local-first generation and embeddings, no required API key.** Chat
  generation runs against a local **Ollama** model by default and chunk
  embeddings are produced in-process with **sentence-transformers** — nothing
  to sign up for, no per-token bill. OpenRouter / OpenAI are available as
  opt-in hosted fallbacks.
- **Multi-tenancy + RBAC + per-document ACLs.** Every document, chunk, and
  conversation is scoped to a workspace; documents can be restricted to specific
  users or roles even within a workspace, enforced by a single choke-point
  query so no retrieval path can accidentally leak a restricted document —
  proven, not just claimed, by an adversarial permission-leakage test that
  checks the restricted chunk ID never appears in a lower-privileged user's
  results at all.
- **Query cache + rate limiting (Redis).** Repeated questions (same workspace,
  user, model, config, and — case/whitespace-insensitive — text) are served
  from cache with no model call; per-user and per-workspace fixed-window rate
  limits.
- **Programmatic access.** Scoped API keys usable on `/search` and `/chat`.

**Trust Layer**

- **Document versioning.** Re-uploading a document creates a new version
  rather than overwriting it; retrieval is scoped to the current version by
  default, and full version history is browsable per document.
- **Cross-document conflict detection.** When retrieved chunks disagree (e.g.
  two policies stating different numbers), a dedicated LLM pass names the
  contradiction as its own signal, surfaced independently of what the answer
  prose happens to lead with.
- **Staleness that reaches the model, not just the UI.** A document's
  freshness is threaded all the way into the generation prompt, with an
  explicit rule requiring a caveat when a claim's only support is stale — the
  fix for a real bug this project's own adversarial testing found (staleness
  was shown in the UI but silently dropped before the LLM ever saw it).
- **"Why this answer?" evidence trail.** Every response carries a full pipeline
  trace (query → retrieve → rerank → evidence → conflicts → version) plus
  per-citation scores (dense, sparse, rerank), freshness, and version number —
  rendered as a readable trace in the UI, not just raw numbers in the payload.
- **Feedback + audit log.** Thumbs up/down on any answer, and every
  security-relevant action (auth, document access changes, feedback) recorded
  to a queryable audit log.
- **Prompt-injection resistant by construction.** Every retrieved chunk is
  wrapped in `<retrieved_chunk>` tags with an explicit system-prompt rule that
  content inside is always data, never an instruction — added proactively,
  verified against real injection attempts (see below), not assumed safe.
- **Adversarially tested, not just eval'd.** A dedicated suite of failure-mode
  and prompt-injection tests, plus a before/after and component ablation study
  quantifying what each Trust Layer piece actually bought (and cost) — see
  [Measured results](#measured-results) for the numbers, including the ones
  that didn't come out favorably.

**Visualization & admin**

- **Living Atlas (React Three Fiber).** A retrieval-reactive 3D visualization —
  the chat panel's answer drives a live camera fly-through of the cited
  documents, with a lit thread between them and brass/red rings marking stale
  or conflicting sources — with a fully-functional 2D fallback and
  reduced-motion support.
- **Admin surfaces.** `/admin/analytics` (live tenant counts, cache size),
  `/admin/content-gaps` (questions the corpus couldn't answer), `/admin/evals`
  (a headline dashboard assembled live from every eval/adversarial/latency
  result file on disk — never hand-typed), `/admin/feedback`, and
  `/admin/audit-log`.

## Architecture

```mermaid
flowchart LR
    subgraph Client["🖥️ Browser"]
        UI["Next.js 14 · App Router<br/>React + Tailwind<br/>React Three Fiber — Living Atlas<br/>evidence trace · conflict/stale rings"]
    end

    subgraph API["⚙️ FastAPI :8000"]
        MW["Auth · RBAC/ACL · rate limit · cache lookup<br/>config_fingerprint() folded into every cache key"]
        R1["/auth /workspaces<br/>/invites /api-keys"]
        R2["/documents<br/>+ /versions /reupload /retry"]
        R3["/search"]
        R4["/chat<br/>+ per-message feedback"]
        R5["/admin/*<br/>analytics · evals · audit-log · feedback"]
    end

    subgraph Agent["🔁 LangGraph agent — bounded to 3 iterations"]
        direction TB
        Plan["plan<br/>condense question → retrieval query"]
        Retrieve["retrieve + rerank<br/>RBAC-scoped hybrid search →<br/>cross-encoder re-score"]
        Assess["assess<br/>LLM sufficiency check"]
        Generate["generate<br/>grounded, cited answer<br/>staleness caveat rule · injection-safe chunk tags"]
        Plan --> Retrieve --> Assess
        Assess -- "insufficient & under bound" --> Plan
        Assess -- "sufficient, or bound hit" --> Generate
    end

    subgraph Trust["🛡️ Trust Layer — post-generation, chat.py"]
        direction TB
        Conflict["conflict detection<br/>cross-document contradiction check"]
        Evidence["evidence build<br/>per-citation scores + staleness + version"]
    end

    subgraph Data["🗄️ Postgres 16 + pgvector · :15432"]
        PG[("chunks: embedding + tsvector<br/>documents · document_versions<br/>workspaces · ACLs · feedback · audit_log")]
    end

    subgraph Cache["⚡ Redis · :6380"]
        RD[("query cache — 1h TTL<br/>fixed-window rate limits")]
    end

    subgraph Ingest["📥 Celery worker"]
        W["parse → chunk → embed → write<br/>new version on re-upload, not overwrite"]
    end

    subgraph LLM["🧠 Generation"]
        OL["Ollama<br/>local, default"]
        OR["OpenRouter<br/>optional fallback"]
    end

    subgraph EMB["🔢 Embeddings"]
        ST["sentence-transformers<br/>local, default"]
        OAI["OpenAI embeddings<br/>optional"]
    end

    UI -- "JWT · X-API-Key · X-Workspace-Id" --> MW
    MW --> R1 & R2 & R3 & R4 & R5
    R4 --> Agent
    Agent --> Trust
    Trust -. "eval/adversarial results feed /admin/evals headline" .-> R5
    R3 --> PG
    Retrieve --> PG
    Conflict --> PG
    Evidence --> PG
    MW <-. "hit / miss, limit check" .-> RD
    Trust -. "write-through" .-> RD
    R2 -. "enqueue on upload" .-> Ingest
    W --> PG
    W -.-> EMB
    Generate --> LLM

    classDef trustLayer fill:#3d2b1f,stroke:#C08A45,color:#f5e6d3,stroke-width:2px
    classDef core fill:#1f2937,stroke:#64748b,color:#e2e8f0
    class Trust,Conflict,Evidence trustLayer
    class Plan,Retrieve,Assess,Generate core
```

*Brass-highlighted nodes are the Trust Layer (T1–T8): everything else is the
baseline RAG loop it was built on top of. The whole diagram is generated from
the real request path in `chat.py` / `agent.py` / `retrieval.py` — not
aspirational.*

## How it works

**1. Sign up, get a workspace.** `POST /auth/signup` creates a user and a personal
workspace; every request after that is scoped to a workspace via the
`X-Workspace-Id` header (defaulted for you if omitted) or via a workspace-bound
API key sent as `X-API-Key`. Roles (`viewer` / `editor` / `admin`) gate write
routes; individual documents can further be restricted to specific users or
roles through a per-document ACL, enforced by a single choke-point query
(`document_visible_clause`) that every retrieval path — search, chat, listing —
goes through, so there's no code path that can accidentally leak a
tenant-scoped or ACL'd document.

**2. Upload a document, it gets ingested asynchronously.** `POST /documents`
stores the file and enqueues a Celery job. The worker runs one pipeline:
**parse → chunk → embed → write.** Parsing extracts text, chunking splits it
into retrieval-sized, structure-aware units, embedding batches the chunks (64
at a time) through the configured embedding backend, and the write step
inserts the new chunks. Re-uploading a document that already exists creates a
**new version** rather than overwriting the old one — the previous version's
chunks stop being retrieved (current-version-only is the default) but stay in
the database, browsable via `GET /documents/{id}/versions`. The document's
status flips to `ready` (or `failed`, with the error captured) when the job
finishes.

**3. Ask a question.** `POST /chat` hands the question to a LangGraph agent with
four nodes and one loop, then runs two more steps once the agent returns:

- **`plan`** — on the first pass, condenses the question (resolving "it" / "that
  policy" against conversation history) into a standalone retrieval query; on
  later passes, uses the refined query the assessment step produced.
- **`retrieve` + rerank** — runs hybrid search *scoped to the caller's
  workspace, ACL visibility, and current document version*: pgvector cosine
  similarity (dense) and Postgres full-text search (sparse) each return
  candidates, merged with Reciprocal Rank Fusion (`1/(k+rank)`, `k=60`) into a
  ranked list. The top candidates are then re-scored by a local cross-encoder
  that reads the query and each chunk's actual text together — a correction
  RRF's rank-only fusion can't make on its own, and measured as the single
  highest-leverage piece of the whole Trust Layer (see
  [Measured results](#measured-results)).
- **`assess`** — an LLM call judges whether the retrieved chunks are enough to
  answer the question. If not, and the loop hasn't hit its bound (3
  iterations), it proposes a refined query and the graph loops back to `plan`.
- **`generate`** — once sufficient (or the bound is hit — the agent always
  answers with what it has rather than looping forever), an LLM call produces
  the answer *and* a citation mapping from each claim to the chunk ID(s) that
  support it. Every chunk reaches the prompt inside `<retrieved_chunk>` tags
  with an explicit system-prompt rule that tagged content is data, never an
  instruction (the prompt-injection defense), and a chunk from a stale,
  unverified document is flagged so the model is told to caveat it rather than
  state it as current fact. If nothing relevant was retrieved, this step is
  what produces the explicit refusal instead of a guess.
- **conflict detection** (after the agent returns, only if there's an answer to
  caveat and more than one source in play) — a dedicated LLM pass checks the
  retrieved chunks for cross-document contradictions and surfaces them as
  their own signal, independent of what the answer prose leads with.
- **evidence build** — for every chunk the answer actually cited, assembles its
  dense/sparse/rerank scores, staleness, and version info into the response's
  `evidence` array — the raw material the frontend's "Why this answer?" trace
  renders, not a blended score.

Before any of that runs, `/chat` checks a Redis cache keyed on
`workspace · user · model · config · normalized(question)` (the config
fingerprint means flipping a retrieval/rerank/conflict-detection flag can
never silently serve an answer computed under a different configuration) — a
repeat question comes back with no model call at all. Every response — cached
or not — carries its citations, conflicts, evidence, and token usage back to
the client.

**4. The answer becomes a map.** The frontend takes the cited chunks and feeds
them to the Living Atlas (`components/living-atlas/LivingAtlas.tsx`, React
Three Fiber): each cited document is a node in 3D space, the camera flies to
frame the ones that answered you, a lit "thread" is drawn between them, and
any node that's stale or in conflict gets its own independent ring (brass for
stale, red for conflict — nested, so both can show on the same node at once) —
literally a route through the corpus with its trust signals visible, not just
a list of links. Reduced-motion or low-power sessions get `Atlas2DFallback`,
an equivalent 2D projection with no WebGL dependency. The same visual language
(compass, terrain, thread field — `components/atlas-world/`) recurs in
smaller, decorative form across the dashboard, search, onboarding, and auth
screens, and the landing page's hero (`components/landing/HeroSurveyScene.tsx`)
is its own standalone survey-route scene rather than a live query result.

### Request lifecycle for `/chat`

```mermaid
sequenceDiagram
    participant U as Browser
    participant API as FastAPI /chat
    participant RBAC as Auth + RBAC/ACL
    participant Cache as Redis cache
    participant Agent as LangGraph agent
    participant DB as Postgres + pgvector
    participant RR as Cross-encoder reranker
    participant LLM as Ollama / OpenRouter

    U->>API: POST /chat { question }
    API->>RBAC: resolve Principal (JWT or API key)
    RBAC-->>API: workspace_id, role
    API->>Cache: lookup cache_key(workspace, user, model, config, question)
    alt cache hit
        Cache-->>API: cached answer + citations + evidence + conflicts
        API-->>U: 200 answer (~20 ms, $0)
    else cache miss
        API->>Agent: run(question, history)
        loop up to 3 iterations
            Agent->>LLM: condense query / assess sufficiency
            Agent->>DB: hybrid search (dense+sparse+RRF), RBAC + ACL + version scoped
            DB-->>Agent: fused candidate chunks
            Agent->>RR: rerank(query, candidates)
            RR-->>Agent: re-scored top-k chunks
        end
        Agent->>LLM: generate grounded, cited answer<br/>(chunks tagged, staleness caveat rule)
        LLM-->>Agent: answer + citations
        Agent-->>API: result + token usage
        opt answerable & >1 source retrieved
            API->>LLM: detect_conflicts(retrieved chunks)
            LLM-->>API: cross-document contradictions, if any
        end
        API->>API: build evidence[] for each cited chunk<br/>(scores + staleness + version)
        API->>Cache: write-through (TTL 1h)
        API-->>U: 200 answer + citations + evidence + conflicts + token usage
    end
```

## Measured results

All numbers below are **measured on this project**, not estimates unless
labelled. The Trust Layer (versioning, reranking, conflict detection, evidence
signals, feedback, expanded eval, adversarial testing, prompt-injection
defense, latency instrumentation) was validated end-to-end in a dedicated
"prove it works" phase — full methodology, raw data, and everything that
didn't go as first expected are in `eval/REPORT.md`; this section is the
summary. Reproduce with the scripts named per section; all of them read
whichever `LLM_PROVIDER` the API is running with. The tables below reflect a
17-question / 7-document corpus snapshot (`eval/corpus/` has since grown to 9
documents for the demo script in `docs/DEMO_SCRIPT.md` — re-running today
will report a larger corpus size, not a regression).

### Before/after — did the Trust Layer help? (`eval/run_before_after.py`)

"Before" = pre-Trust-Layer hybrid retrieval (no reranking, no version scoping,
no conflict detection). "After" = the full current system. Same corpus, same
17 questions, same local Ollama model (`qwen2.5:3b`), back-to-back:

| Metric | Before | After | Δ |
| --- | --- | --- | --- |
| Answer accuracy | 92.9% | 92.9% | no change |
| Retrieval hit rate | 100% | 100% | no change |
| Citation grounding | 80.0% | 85.7% | **+5.7 pts** |
| Citation coverage (claim-level) | 43.3% | 75.0% | **+31.7 pts** |
| Conflict detection accuracy | N/A (detection was off) | 25.0% | — |
| Refusal accuracy | 100% | 100% | no change |
| Permission leakage | 0 | 0 | no change |
| Avg tokens / query | 1,182 | 2,168 | **+83% (worse)** |
| Latency p50 | 3.0 s | 6.9 s | **+129% (worse)** |

The Trust Layer's real win is citation quality (coverage nearly doubled), not
retrieval hit rate (already 100% before, on this corpus). It also has a real,
measured cost: latency and token spend both roughly doubled — mostly from
conflict detection's extra LLM call (see the latency breakdown below).

### Ablation — which component actually did that? (`eval/run_before_after.py --out-prefix ablation`)

| Config | Retrieval hit rate | Citation accuracy | Citation coverage | Answer accuracy |
| --- | --- | --- | --- | --- |
| A — dense only | 100% | 80.0% | 50.0% | 85.7% |
| B — dense+sparse, no RRF | N/A — not a real code path in this system | | | |
| C — hybrid + RRF | 100% | 80.0% | 43.3% | 92.9% |
| D — C + reranking | 100% | 85.7% | **82.1%** | 92.9% |
| E — full Trust Layer | 100% | **92.9%** | 75.0% | 92.9% |

**Reranking (C→D) was the standout single addition** — citation coverage
nearly doubled at essentially zero latency cost (it's a local cross-encoder
pass, not an LLM call). Conflict detection (D→E) is the only addition with a
real, consistent cost and the weakest accuracy of the bunch — see below.

### Adversarial & security testing

Pass/fail, not graded — see `eval/REPORT.md` for full detail and
`eval/adversarial/` / `eval/run_adversarial.py` / `eval/run_prompt_injection.py`
for the suites themselves.

- **Adversarial failure modes (`eval/run_adversarial.py`): 6/7 passed.**
  No-answer refusal, conflict surfacing, staleness caveats (fixed a real bug
  found here — see below), permission leakage (verified by checking the
  restricted chunk ID never appears in a lower-privileged user's results, not
  by scanning answer text), multi-hop retrieval with claim-level citations,
  and claim-citation coverage all pass. The one accepted failure: chat cannot
  answer "what did the 2024 version say" — it safely refuses rather than
  silently answering with current-version content, but doesn't return the
  historical answer either. Fixing that needs real NL version-intent
  detection, a new capability rather than a bug fix, so it's documented as a
  known limitation rather than built under the freeze.
- **Prompt injection (`eval/run_prompt_injection.py`): 3/3 attempts correctly
  ignored.** Three forms tested — a blunt "SYSTEM OVERRIDE" instruction in
  normal prose, one hidden in an HTML comment styled as metadata, and a fake
  multi-turn conversation claiming the model had already agreed to drop its
  restrictions. All three were retrieved into context (confirmed via
  `retrieved_doc_count`, not assumed) and none were obeyed. **Defense
  mechanism**: every retrieved chunk is wrapped in `<retrieved_chunk
  id="...">...</retrieved_chunk>` tags, and the system prompt explicitly
  states that content inside those tags is always data, never an instruction,
  naming the exact attack patterns tested — added *proactively*, since
  passing 3/3 without any structural boundary would only prove this specific
  local model didn't take the bait, not that the architecture was sound.
- **A real bug found and fixed by this testing**: a document's staleness was
  shown in the UI but never reached the LLM's own prompt, so a stale,
  never-verified source got stated as a plain confident fact. Fixed by
  threading staleness into the retrieval/generation pipeline and adding an
  explicit prompt rule requiring a caveat when a claim's only support is
  stale.

### Latency breakdown by stage (`app/timing.py`, local Ollama, steady state)

| Stage | p50 | p95 |
| --- | --- | --- |
| auth | 4.0 ms | 7.4 ms |
| retrieval (dense+sparse+RRF) | 17.1 ms | 41.8 ms |
| reranking (cross-encoder) | 64.6 ms | 107.3 ms |
| generation | 4,027.3 ms | 6,003.6 ms |
| conflict detection | 4,481.8 ms | 4,913.3 ms |
| **total** | **8,651.6 ms** | **10,590.7 ms** |

Generation and conflict detection are **co-equal** bottlenecks — conflict
detection's p50 is actually slightly *higher* than generation's, and together
they're 98.4% of total latency. Retrieval, reranking, and auth combined are
under 1%. Conflict detection already skips single-source answers at zero
cost (confirmed still in place, not a new optimization); the remaining cost
is inherent to it being a second real LLM call, not a wasteful pattern.

### Original quality gate (`eval/run_eval.py`, still runs, still served at `/admin/evals`)

8-question labelled set over the original 4-document corpus, generation model
`nvidia/nemotron-nano-9b-v2:free` (OpenRouter free tier, kept as a
reproducible non-local reference point): 100% answer accuracy, citation
grounding, refusal accuracy, and retrieval hit rate, ~2,118 avg tokens/query.
Superseded in scope (not accuracy) by the 17-question corpus above, but still
the fastest single command to sanity-check a change:
`uv run python eval/run_eval.py`.

### Latency & throughput (`eval/load_test.py`, single API worker, rate-limiter off)

| Path | p50 | p95 | Throughput | Cache hit |
| --- | --- | --- | --- | --- |
| `/search` cold (cache miss) | **75 ms** | **101 ms** | 127 req/s | — |
| `/search` warm (cache hit) | **29 ms** | **49 ms** | **627 req/s** | 100% |
| `/chat` cold (agent + LLM) | **23.2 s** | **31.2 s** | — | — |
| `/chat` warm (cache hit) | **20 ms** | **45 ms** | **418 req/s** | 100% |

- **Retrieval is sub-100 ms** at p50/p95 (hybrid dense + FTS + RRF).
- **`/chat` cold latency is dominated by the model call**, not AtlasKB: the
  free-tier hosted model measured above is slow and the agent can make several
  calls in one turn. The cache turns a repeated question from
  **~23 s → ~20 ms (~1000×)** and **$0 model cost**.

### Cost per query

- **$0** with the default local Ollama provider — no API calls leave the machine.
- **$0 measured** on the OpenRouter free-tier model used for the smaller eval
  above; **$0** for any cache hit regardless of provider (no model call).
- Token spend depends on how much of the Trust Layer is active: **1,182
  tokens/query** with conflict detection off, **2,168 tokens/query** with the
  full system on (measured, before/after table above) — conflict detection's
  extra LLM call is most of that difference. At the higher figure, projected
  cost on paid small hosted models is roughly **$0.003–0.007 / query** (e.g.
  Claude Haiku 4.5 / GPT-5.1 rates) — a projection, not billed.

## Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic,
  Postgres 16 + **pgvector**, Redis, Celery, **LangGraph**, OpenAI-compatible
  client (→ local Ollama by default, OpenRouter optional), sentence-transformers,
  argon2 + PyJWT, structlog.
- **Frontend:** Next.js 14 (App Router, TypeScript), Tailwind, **React Three Fiber
  / drei / three**, Playwright (e2e).
- **Tooling:** `uv` workspace (api + workers), Docker Compose (Postgres/Redis),
  ruff, pytest.

## Quickstart

Prerequisites: Docker, [`uv`](https://docs.astral.sh/uv/), Node 20+,
[Ollama](https://ollama.com) (for the default local LLM — skip if you'll run
with `LLM_PROVIDER=openrouter` instead).

```bash
# 0. Install + configure (from the repo root)
uv sync --all-packages
cp .env.example .env         # set POSTGRES_PASSWORD, JWT_SECRET
                              # (only needed if you're using LLM_PROVIDER=openrouter: OPENROUTER_API_KEY)

# 0b. Pull the local model (skip if using OpenRouter instead)
ollama pull qwen3:8b
ollama serve                  # if not already running as a background service

# 1. Infra: Postgres+pgvector (host 15432) and Redis (host 6380)
docker compose up -d postgres redis

# 2. Database schema
set -a && . ./.env && set +a
(cd apps/api && uv run alembic upgrade head)

# 3. API  (terminal 1)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Worker  (terminal 2) — --pool=solo: PyTorch's Metal backend aborts in a forked worker on macOS
uv run celery -A atlaskb_workers.celery_app worker --loglevel=info --pool=solo

# 5. Web  (terminal 3)
cd apps/web && npm install && npm run dev      # http://localhost:3000
```

- Embeddings default to a local sentence-transformers model (no key; downloads
  on first use, `EMBEDDING_BACKEND=openai` is the alternative).
- `/chat` generation defaults to local Ollama (`qwen3:8b`, no key needed —
  `GET /health/llm` reports whether it's reachable and the model is pulled). Set
  `LLM_PROVIDER=openrouter` plus `OPENROUTER_API_KEY` to use a hosted model
  instead; `OPENROUTER_MODEL` picks the slug (a `:free` slug works with no
  credits).
- Secrets are read from the environment / `.env` — the app refuses to boot if
  `DATABASE_URL` or `JWT_SECRET` is unset; no credential literals live in source.

## Tests, eval & load

```bash
# Backend unit + integration tests (real Postgres+pgvector, dedicated Redis DB)
cd apps/api && uv run pytest                     # 111 passing

# Frontend end-to-end (Playwright drives signup→upload→ask→cited answer, +atlas)
cd apps/web && npx playwright install chromium && npm run test:e2e

# Quality eval → writes eval/results/latest.json (served at /admin/evals)
uv run python eval/run_eval.py

# Before/after + ablation → writes eval/results/before_after*.json, ablation*.json
# (run once per config; see eval/README.md for the T9.0 component-toggle flags
# and the exact "before"/"after"/A-E configurations)
uv run python eval/run_before_after.py --label after

# Adversarial failure-mode + prompt-injection suites (pass/fail, not graded)
uv run python eval/run_adversarial.py
uv run python eval/run_prompt_injection.py

# Load test → writes eval/results/load-latest.json
#   run the API with RATE_LIMIT_ENABLED=false so the limiter doesn't distort latency
uv run python eval/load_test.py
```

Full before/after and ablation methodology, everything that didn't go as
first expected, and per-question raw data: `eval/REPORT.md`.

## API surface

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/auth/signup` · `/auth/login` · `/auth/refresh` | — | JWT auth |
| POST/GET | `/workspaces`, `/workspaces/{id}/members`, `/workspaces/{id}/invites` | JWT | Workspaces, members, roles |
| GET/POST | `/invites/{token}`, `/invites/{token}/accept` | JWT | Accept a workspace invite |
| POST/GET/DELETE | `/api-keys` | JWT | Scoped programmatic keys |
| POST/GET | `/documents`, `/documents/{id}`, `/documents/{id}/access` | JWT | Upload, list, detail, per-document ACLs |
| POST | `/documents/{id}/verify` | JWT | Re-run/confirm ingestion status |
| POST | `/documents/{id}/reupload`, `/documents/{id}/retry` | JWT | Re-upload a new version, retry a failed ingest |
| GET | `/documents/{id}/versions` | JWT | Document version history (Trust Layer T1) |
| GET | `/dashboard/relief` | JWT | Workspace-level summary data |
| POST | `/search` | JWT / API key | Raw hybrid retrieval (ranked chunks + scores) |
| POST | `/chat` | JWT / API key | Grounded answer + citations + token usage |
| GET | `/conversations`, `/conversations/{id}` | JWT | Conversation history |
| POST | `/chat/messages/{id}/feedback` | JWT | Thumbs up/down on an answer (Trust Layer T6) |
| GET | `/admin/analytics`, `/admin/evals`, `/admin/content-gaps`, `/admin/query-volume` | JWT (admin) | Tenant analytics, eval results (incl. T9.8 headline), unanswered questions |
| GET | `/admin/audit-log`, `/admin/feedback` | JWT (admin) | Audit trail, aggregated answer feedback (Trust Layer T6) |
| GET | `/health`, `/health/llm` | — | Liveness, LLM provider reachability |

The workspace is selected with the optional `X-Workspace-Id` header (defaults to
the user's personal workspace); `X-API-Key` authenticates programmatic calls and
carries its own fixed workspace and role.

## Repository layout

```
atlaskb/
  apps/
    web/       # Next.js 14 frontend (+ Living Atlas, Playwright e2e)
    api/       # FastAPI service (auth, RBAC, retrieval, agent, cache, admin)
    workers/   # Celery ingestion worker (calls into apps/api's ingest pipeline)
  eval/        # eval + load-test harnesses, corpus, results/
  infra/       # docker/ (Dockerfiles), k8s/, terraform/
  docs/        # design plan + media + docs/DEMO_SCRIPT.md (live walkthrough script)
  docker-compose.yml
```

## Status

Feature-complete reference implementation: multi-tenant auth/RBAC/ACL, async
ingestion, hybrid retrieval, an agentic cited-answer pipeline with local-first
generation and embeddings, a query cache + rate limiting, API keys, the 3D
Living Atlas with a 2D fallback, and admin analytics/evals/content-gap
surfaces — all covered by automated tests and the measured results above.

On top of that base, a **Trust Layer** (document versioning, structure-aware
chunking, reranking, cross-document conflict detection, per-answer evidence
and a "Why this answer?" pipeline trace, a feedback/audit log, and an
expanded eval suite) was built and then, in phase T9, put under adversarial
and before/after measurement rather than taken on faith — see *Measured
results* above for what actually changed and what didn't.

**The feature set is now frozen.** From here, only bug fixes, UX polish,
documentation, and additional test coverage — no new capabilities — until a
new phase is explicitly scoped.
