# syntax=docker/dockerfile:1
# AtlasKB Celery worker image.
# Build context is the repo root (see docker-compose.yml); the worker depends on
# the API's `app` package via the uv workspace, so both sources are needed.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/workers/pyproject.toml apps/workers/pyproject.toml
# Trust Layer T11.3: see infra/docker/api.Dockerfile's matching comment --
# a build-scoped cache mount so a retried/incremental build reuses
# already-downloaded wheels instead of re-fetching several GB from scratch.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package atlaskb-workers --no-install-workspace --no-dev --frozen

# The worker imports the shared pipeline from apps/api and its own task package.
COPY apps/api apps/api
COPY apps/workers apps/workers
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package atlaskb-workers --no-dev --frozen

ENV PATH="/app/.venv/bin:$PATH"

# --pool=solo: PyTorch's Metal/CUDA init can abort inside a forked worker; the
# solo pool avoids forking. Embeddings run on CPU (EMBEDDING_DEVICE=cpu).
CMD ["celery", "-A", "atlaskb_workers.celery_app", "worker", "--loglevel=info", "--pool=solo"]
