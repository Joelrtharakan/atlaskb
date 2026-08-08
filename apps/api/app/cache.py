"""Redis-backed semantic cache for the query path.

The cache key hashes the normalized query together with the tenant, the user,
and the model. Tenant + user are part of the key so a cached answer can never
leak across tenants, nor across users whose per-document ACLs may differ — a
correctness/isolation property, not just a namespacing convenience.

"Semantic" here is normalized-exact: queries that differ only in case or
whitespace collapse to the same key. (A future version could key on an embedding
bucket; the interface would not change.)
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.config import settings
from app.redis_client import get_redis

_WS = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    return _WS.sub(" ", query.strip().lower())


def cache_key(*, namespace: str, workspace_id: str, user_id: str, model: str, query: str) -> str:
    digest = hashlib.sha256(
        "\x1f".join([workspace_id, user_id, model, normalize_query(query)]).encode("utf-8")
    ).hexdigest()
    return f"{settings.cache_prefix}:{namespace}:{digest}"


def cache_get(key: str) -> dict[str, Any] | None:
    if not settings.cache_enabled:
        return None
    try:
        raw = get_redis().get(key)
    except Exception:  # noqa: BLE001 - a cache outage must never break the request
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_set(key: str, value: dict[str, Any]) -> None:
    if not settings.cache_enabled:
        return
    try:
        get_redis().set(key, json.dumps(value), ex=settings.cache_ttl_seconds)
    except Exception:  # noqa: BLE001 - best-effort write-through; next call recomputes
        return
