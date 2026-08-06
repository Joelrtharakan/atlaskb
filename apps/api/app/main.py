from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import settings
from app.logging_config import configure_logging, get_logger

configure_logging(settings.log_level)
log = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api.startup", app_name=settings.app_name)
    yield
    log.info("api.shutdown", app_name=settings.app_name)


app = FastAPI(title="AtlasKB API", version="0.0.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
