"""Database engine, session factory, and declarative base."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env at the repo root and fill it in "
        "(see README). If your .env is elsewhere, export DATABASE_URL before starting."
    )

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Trust Layer T11.2: explicit, configurable pool sizing so a horizontally
    # scaled deployment's real connection ceiling (replicas * (pool_size +
    # max_overflow)) is a deliberate number checked against Postgres's own
    # max_connections, not whatever SQLAlchemy's single-instance defaults
    # happened to be.
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
