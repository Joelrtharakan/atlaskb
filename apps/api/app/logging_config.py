"""Structured JSON logging configured from the start.

Both stdlib logging (used by uvicorn) and structlog emit JSON lines so that
every log record — application or server — is machine-parseable from day one.
"""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    level = logging.getLevelName(log_level.upper())

    # Processors shared between structlog and stdlib-originated records.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Route uvicorn's loggers through our JSON handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = [handler]
        uv_logger.propagate = False
        uv_logger.setLevel(level)


def get_logger(*args, **kwargs) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(*args, **kwargs)
