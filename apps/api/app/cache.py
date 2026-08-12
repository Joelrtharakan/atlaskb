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


def cache_key(
    *, namespace: str, workspace_id: str, user_id: str, model: str, query: str, epoch: int
) -> str:
    """``epoch`` is required, not optional-with-a-default: it's how a
    workspace's cache gets invalidated (Trust Layer Phase 8 — see
    ``bump_workspace_epoch``), and a forgettable default risks a new call
    site quietly never invalidating. Every current call site passes
    ``get_workspace_epoch(principal.workspace_id)``."""
    digest = hashlib.sha256(
        "\x1f".join([workspace_id, user_id, model, normalize_query(query), str(epoch)]).encode("utf-8")
    ).hexdigest()
    return f"{settings.cache_prefix}:{namespace}:{digest}"


def _epoch_key(workspace_id: str) -> str:
    return f"{settings.cache_prefix}:epoch:{workspace_id}"


def get_workspace_epoch(workspace_id: str) -> int:
    """Current cache-invalidation generation for a workspace, folded into
    every cache key (Trust Layer Phase 8). Bumping it (see
    ``bump_workspace_epoch``) makes every previously-cached answer for that
    workspace unreachable on the next lookup — the standard "cache
    versioning" pattern, chosen over enumerating and deleting individual
    keys because Redis has no reverse index from workspace to the cache
    keys it produced, and versioning needs no such index. Defaults to 0
    (never bumped) — including on a cache outage, since "no invalidation
    happened" is the safe direction to fail in (a miss just recomputes)."""
    try:
        raw = get_redis().get(_epoch_key(workspace_id))
    except Exception:  # noqa: BLE001 - cache outage must never break the request
        return 0
    return int(raw) if raw else 0


def bump_workspace_epoch(workspace_id: str) -> None:
    """Invalidate every cached /chat and /search answer for a workspace.

    Call this on any event that can change what a cached answer *should*
    have said: a document's content changes (upload, reupload — a new or
    changed document can turn a cached refusal into a stale wrong answer,
    not just a stale right one), its ACL changes, or a member's role/
    membership changes (changes what they're allowed to see). Never raises:
    a failed bump degrades to "not invalidated this time" rather than
    blocking the write that triggered it — the write already succeeded, and
    the entry still expires via TTL (``cache_ttl_seconds``) in the worst
    case, same bound as before this phase existed.
    """
    try:
        get_redis().incr(_epoch_key(workspace_id))
    except Exception:  # noqa: BLE001 - a failed bump must never block the write that triggered it
        return


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
