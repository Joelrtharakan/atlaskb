# AtlasKB

AtlasKB is a multi-tenant, agentic RAG knowledge platform: teams ingest their
documents into isolated tenant workspaces, and an agent-driven retrieval pipeline
answers questions with citations grounded in that tenant's knowledge base. This
repository contains the web frontend, the API, and the async worker fleet that
will power ingestion, embedding, and retrieval.

**Status: scaffold.** This phase only sets up a repository skeleton that builds
and runs. There is no business logic, authentication, or database schema yet —
just the services wired together so `docker compose up` brings the stack online.

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

### API

The API is managed with [uv](https://docs.astral.sh/uv/).

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

### Workers

```bash
cd apps/workers
uv sync
uv run celery -A atlaskb_workers.celery_app worker --loglevel=info
```
