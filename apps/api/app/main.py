import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.logging_config import configure_logging, get_logger
from app.routers import (
    admin,
    apikeys,
    auth,
    chat,
    conversations,
    documents,
    invites,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _require_runtime_secrets()
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

    return LLMHealthResponse(**ollama_health())


app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(invites.router)
app.include_router(apikeys.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(conversations.router)
app.include_router(search.router)
app.include_router(chat.router)
