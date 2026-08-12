"""Lightweight per-stage wall-clock timing (Trust Layer T9.5).

No OpenTelemetry (or any other tracing) exists in this codebase, and adding a
full tracing stack — a new dependency, an exporter, a collector — is exactly
the kind of new capability T9 says not to start mid-phase. This is the
narrower thing T9.5 actually asked for if tracing doesn't already exist:
purpose-built timing spans around each /chat stage, accumulated per request
and returned only when explicitly requested (never exposed to a normal
client by default).
"""

from __future__ import annotations

import time
from contextlib import contextmanager


class StageTimer:
    """Accumulates elapsed milliseconds per named stage across a single
    request. A stage entered multiple times (e.g. "retrieval" across several
    agent iterations) sums its durations rather than overwriting them."""

    def __init__(self) -> None:
        self._totals: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._totals[name] = self._totals.get(name, 0.0) + elapsed_ms

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 1) for k, v in self._totals.items()}
