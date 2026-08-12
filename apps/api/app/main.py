import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.llm import ollama_health
from app.logging_config import configure_logging, get_logger
from app.routers import (
    admin,
    apikeys,
    auth,
    chat,
    connectors,
    conversations,
    dashboard,
    documents,
    invites,
    oidc,
    search,
    workspaces,
)

configure_logging(settings.log_level)
log = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str


class LLMHealthResponse(BaseModel):
    provider: str
    model: str
    reachable: bool
    model_available: bool
    # Trust Layer T11.1: makes the generation concurrency limiter an
    # observable number instead of a silent bottleneck — active_generations
    # is a live, cross-replica count (Redis-backed), not per-process.
    active_generations: int
    concurrency_limit: int


def _require_runtime_secrets() -> None:
    """Fail fast if required secrets are unset — no baked-in defaults to fall
    back on, so the API can never silently run on placeholder credentials."""
    missing = [
        name
        for name, value in (("DATABASE_URL", settings.database_url), ("JWT_SECRET", settings.jwt_secret))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required configuration: {', '.join(missing)}. "
            "Set them in the environment / .env (see .env.example)."
        )


def _ensure_ollama_running() -> None:
    """Local dev convenience: when the API is run directly on the host (``uv
    run uvicorn ...``) with the default Ollama provider, start the Ollama
    server automatically if it isn't already up — so ``/chat`` works without a
    separate manual ``ollama serve`` step.

    Skipped for the Docker path: there ``OLLAMA_BASE_URL`` points at
    ``host.docker.internal`` (see docker-compose.yml), since Ollama runs on
    the host and starting it is the host's job, not a container's. Also
    skipped outright for any non-Ollama provider.
    """
    if settings.llm_provider != "ollama":
        return
    host = urlparse(settings.ollama_base_url).hostname
    if host not in ("127.0.0.1", "localhost"):
        return
    if ollama_health()["reachable"]:
        return
    if shutil.which("ollama") is None:
        log.warning(
            "ollama.not_installed",
            hint="install from https://ollama.com, or set LLM_PROVIDER=openrouter",
        )
        return
    log.info("ollama.autostart", model=settings.ollama_model)
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Best-effort: give it a few seconds to bind before we start serving
    # /chat traffic. If it's still not up, /health/llm just reports that —
    # nothing here blocks the API from starting.
    for _ in range(10):
        time.sleep(0.5)
        if ollama_health()["reachable"]:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    _require_runtime_secrets()
    _ensure_ollama_running()
    log.info("api.startup", app_name=settings.app_name)
    yield
    log.info("api.shutdown", app_name=settings.app_name)


app = FastAPI(title="AtlasKB API", version="0.0.0", lifespan=lifespan)

# Allow the web app (a separate origin) to call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Structured access log with a per-request id bound to all log lines."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id, method=request.method, path=request.url.path
    )
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request.error")
        raise
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info("request.complete", status_code=response.status_code, duration_ms=duration_ms)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/llm", response_model=LLMHealthResponse)
async def health_llm() -> LLMHealthResponse:
    """LLM/Ollama availability. Reported separately from ``/health`` so a down LLM
    never marks the whole API unhealthy — the app still serves auth, docs, search."""
    from app.llm import ollama_health
    from app.llm_concurrency import active_generations

    return LLMHealthResponse(
        **ollama_health(),
        active_generations=active_generations(),
        concurrency_limit=settings.llm_concurrency_limit,
    )


app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(invites.router)
app.include_router(apikeys.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(conversations.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(connectors.router)
app.include_router(oidc.router)
