# AtlasKB Celery worker image.
# Build context is apps/workers (see docker-compose.yml).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev

COPY . .
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["celery", "-A", "atlaskb_workers.celery_app", "worker", "--loglevel=info"]
