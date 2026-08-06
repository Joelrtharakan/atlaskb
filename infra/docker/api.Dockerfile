# AtlasKB API image.
# Build context is apps/api (see docker-compose.yml).
FROM python:3.12-slim

# Install uv (fast, reproducible Python dependency management).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev

# Copy the application source.
COPY . .
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
