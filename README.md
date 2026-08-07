# AtlasKB

AtlasKB is a multi-tenant, agentic RAG knowledge platform: teams ingest their
documents into isolated tenant workspaces, and an agent-driven retrieval pipeline
answers questions with citations grounded in that tenant's knowledge base. This
repository contains the web frontend, the API, and the async worker fleet that
will power ingestion, embedding, and retrieval.

**Status: backend MVP.** Single-user Q&A over uploaded documents works end to
end: JWT auth, PDF/Markdown/HTML upload with async ingestion (parse → chunk →
embed → pgvector), hybrid retrieval (dense cosine + Postgres full-text, fused
with RRF), and grounded generation with citations via OpenRouter. Multi-tenancy,
the agent loop, and caching are intentionally out of scope for this phase (a
`tenant_id` placeholder column exists so the schema is forward-compatible).

See [Backend MVP](#backend-mvp-local-quickstart) below for the quickstart and a
verified end-to-end curl sequence.

## Services

| Service   | Stack                                   | Local port |
| --------- | --------------------------------------- | ---------- |
| `web`     | Next.js 14 (App Router, TS, Tailwind)   | 3000       |
| `api`     | FastAPI (Python 3.12, Pydantic v2)      | 8000       |
| `workers` | Celery (Redis broker)                   | —          |
| `postgres`| `pgvector/pgvector` (Postgres 16)       | 15432      |
| `redis`   | Redis 7                                 | 6380       |

> Host ports 15432/6380 map to the containers' standard 5432/6379 to avoid
> clashing with a Postgres/Redis you may already run locally.

## Run locally

Prerequisites: Docker + Docker Compose.

```bash
docker compose up --build
```

Then:

- Web UI: http://localhost:3000
- API health check: http://localhost:8000/health → `{"status":"ok"}`
- API docs: http://localhost:8000/docs

Stop and clean up:

```bash
docker compose down -v
```

> **Note (backend MVP):** the `api`/`workers` images build from the repo root as
> a uv workspace and pull a local ML/embeddings stack, so first build is large.
> The **verified** path for this phase is running Postgres + Redis via compose
> and the API + worker locally with `uv` — see
> [Backend MVP (local quickstart)](#backend-mvp-local-quickstart).

## Repository layout

```
atlaskb/
  apps/
    web/            # Next.js 14 frontend
    api/            # FastAPI service (uv-managed)
    workers/        # Celery worker package
  infra/
    docker/         # Dockerfiles for web, api, workers
    k8s/            # Kubernetes manifests (placeholder)
    terraform/      # Infra as code (placeholder)
  eval/             # RAGAS eval datasets/scripts (placeholder)
  .github/workflows # CI (placeholder)
  docker-compose.yml
```

## Local development (outside Docker)

The API and workers form a single [uv](https://docs.astral.sh/uv/) **workspace**
(`apps/api` + `apps/workers` share the domain layer in `app/`). Sync and run
everything from the repo root:

```bash
uv sync --all-packages
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

See the Backend MVP quickstart below for running the API, worker, and database.

## Backend MVP (local quickstart)

Run all commands **from the repo root** (so `.env` is picked up).

```bash
# 0. Dependencies + config
uv sync --all-packages
cp .env.example .env          # fill in OPENROUTER_API_KEY to enable /chat

# 1. Infra (Postgres+pgvector on 15432, Redis on 6380)
docker compose up -d postgres redis

# 2. Database schema
cd apps/api && DATABASE_URL="postgresql+psycopg://atlaskb:atlaskb@localhost:15432/atlaskb" \
  uv run alembic upgrade head && cd ../..

# 3. API (terminal 1)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Worker (terminal 2)
#    --pool=solo avoids a macOS crash where PyTorch's Metal backend aborts
#    inside a forked Celery worker (embeddings run on CPU regardless).
uv run celery -A atlaskb_workers.celery_app worker --loglevel=info --pool=solo
```

- Embeddings default to a local `sentence-transformers` model (no API key; the
  model downloads on first use). Set `EMBEDDING_BACKEND=openai` to use the
  OpenAI embeddings API instead. Embeddings never go through OpenRouter.
- `/chat` generation goes through OpenRouter; set `OPENROUTER_API_KEY` and
  optionally `OPENROUTER_MODEL` (see `.env.example`).

### Endpoints

| Method | Path                | Auth | Purpose                                        |
| ------ | ------------------- | ---- | ---------------------------------------------- |
| POST   | `/auth/signup`      | —    | Create a user                                  |
| POST   | `/auth/login`       | —    | Get an access + refresh token pair             |
| POST   | `/auth/refresh`     | —    | Exchange a refresh token for a new pair        |
| POST   | `/documents`        | JWT  | Upload a PDF/MD/HTML; enqueues async ingestion |
| GET    | `/documents`        | JWT  | List documents with status                     |
| GET    | `/documents/{id}`   | JWT  | Document detail incl. chunk count              |
| POST   | `/search`           | JWT  | Raw hybrid retrieval (ranked chunks + scores)  |
| POST   | `/chat`             | JWT  | Grounded answer with citations → chunk IDs     |

### End-to-end curl sequence

```bash
API=http://127.0.0.1:8000

# signup + login
curl -s -X POST $API/auth/signup -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password123"}'
ACCESS=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"password123"}' | jq -r .access_token)

# upload a PDF -> returns {"id": ..., "status": "processing"}
DOC=$(curl -s -X POST $API/documents -H "Authorization: Bearer $ACCESS" \
  -F "file=@mydoc.pdf;type=application/pdf" | jq -r .id)

# poll until ready
until [ "$(curl -s $API/documents/$DOC -H "Authorization: Bearer $ACCESS" | jq -r .status)" = ready ]; do
  sleep 2; done
curl -s $API/documents/$DOC -H "Authorization: Bearer $ACCESS" | jq   # shows chunk_count

# inspect retrieval directly
curl -s -X POST $API/search -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"query":"your question","top_k":5}' | jq

# grounded, cited answer (returns "cannot answer" if not supported by chunks)
curl -s -X POST $API/chat -H "Authorization: Bearer $ACCESS" \
  -H 'Content-Type: application/json' -d '{"question":"your question"}' | jq
```

`/chat` returns structured JSON: `answerable`, `answer`, `citations` (each
mapping a `claim` to the `chunk_ids` that support it), and the `retrieved`
chunks with their fused/dense/sparse scores.

### Tests

```bash
cd apps/api && uv run pytest
```

Unit tests cover chunking and RRF ranking; integration tests run `/auth`,
`/documents`, `/search`, and `/chat` against a **real** Postgres+pgvector test
database (created automatically as `atlaskb_test` on the compose Postgres).

## Frontend MVP (local quickstart)

The web app (`apps/web`) is a Next.js 14 + TypeScript + Tailwind client wired to
the Phase 2 API. It applies the Phase 1 cartography design tokens/typography but
**does not** render the 3D Living Atlas yet — plain, well-typeset UI only.

Pages: `/login`, `/signup`, `/documents` (register + upload with a contour-line
progress indicator that polls to ready/failed), `/documents/[id]` (metadata +
chunk count), `/search` (raw hybrid results with dense/sparse/fused scores), and
`/chat` (grounded answers with inline `[n]` citation markers that expand to the
source chunk + page).

**1. Run the backend** (see the Backend MVP quickstart above): Postgres + Redis
via compose, plus the API and worker locally. `/chat` needs `OPENROUTER_API_KEY`
set in `.env`.

**2. Run the web app** (separate terminal):

```bash
cd apps/web
npm install
# API base URL — defaults to http://localhost:8000 if unset:
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev            # http://localhost:3000
```

The API enables CORS for `http://localhost:3000` and `http://127.0.0.1:3000`
(configurable via the `CORS_ORIGINS` setting).

### End-to-end test

One Playwright test drives the whole product loop against the real backend:
**sign up → upload a document → wait until ready → ask a question → see a cited
answer on screen** (and expands the citation to its source).

```bash
# With Postgres + Redis + API + worker already running (and OPENROUTER_API_KEY set):
cd apps/web
npm install
npx playwright install chromium   # first time only
npm run test:e2e
```

Playwright starts the Next.js dev server itself; it expects the backend to be up
(it will reuse an already-running dev server on :3000). Verified passing:
`1 passed` in ~30s.
