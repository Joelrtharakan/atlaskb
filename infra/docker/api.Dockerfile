# syntax=docker/dockerfile:1
# AtlasKB API image.
# Build context is the repo root (see docker-compose.yml) because the API and
# workers form a single uv workspace and share the `app` package.
FROM python:3.12-slim

# Install uv (fast, reproducible Python dependency management).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Resolve dependencies from the workspace lockfile first for better caching.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/workers/pyproject.toml apps/workers/pyproject.toml
# Trust Layer T11.3: mounts uv's package cache into the build (not baked
# into the image layer) so a retried/incremental build reuses already-
# downloaded wheels instead of re-fetching several GB of ML dependencies
# (torch/CUDA wheels alone are ~2GB) from scratch on every build attempt --
# found the hard way when a transient network failure mid-download meant a
# from-scratch retry with no mount here.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package atlaskb-api --no-install-workspace --no-dev --frozen

# Copy the API source and install the package itself.
COPY apps/api apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package atlaskb-api --no-dev --frozen

ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app/apps/api
EXPOSE 8000
# Apply migrations, then serve. DATABASE_URL is supplied via the environment.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
