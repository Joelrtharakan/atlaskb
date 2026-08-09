"""Content-gap detection for the Fog-of-War admin view.

A "gap" is a question the assistant could not answer from the documents. We find
those turns (assistant reply == the CANNOT_ANSWER sentinel), take the user
question that prompted each, and cluster near-duplicate questions by embedding
similarity so a repeated blind-spot shows as one thicker patch of fog rather than
many. Gaps are derived on the fly; only resolution state is persisted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings import embed_query
from app.llm import CANNOT_ANSWER
from app.models import Message

# Cosine similarity at/above which two questions are treated as the same gap.
_SIM_THRESHOLD = 0.72
# Cap work per request — plenty for an admin view, bounds embedding cost.
_MAX_TURNS = 200


@dataclass
class _Item:
    text: str
    count: int
    last_seen: datetime
    emb: list[float]


@dataclass
class GapCluster:
    key: str
    query: str
    count: int
    last_seen: datetime
    x: float
    y: float
    radius: float
    resolved: bool = False
    members: list[str] = field(default_factory=list)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _unanswered_questions(db: Session, workspace_id: str) -> list[tuple[str, datetime]]:
    """(question, timestamp) for each turn the assistant couldn't answer."""
    rows = db.execute(
        select(Message.conversation_id, Message.role, Message.content, Message.created_at)
        .where(Message.workspace_id == workspace_id)
        .order_by(Message.conversation_id, Message.created_at, Message.id)
    ).all()
    out: list[tuple[str, datetime]] = []
    prev: dict[str, tuple[str, str, datetime]] = {}
    for conv, role, content, created in rows:
        if role == "assistant" and content.strip() == CANNOT_ANSWER:
            p = prev.get(conv)
            if p and p[0] == "user" and p[1].strip():
                out.append((p[1].strip(), p[2]))
        prev[conv] = (role, content, created)
    return out[-_MAX_TURNS:]


def _placement(key: str) -> tuple[float, float]:
    """Deterministic (x,y) in the interior of the map from the gap key, so a
    given gap always fogs the same region."""
    h = hashlib.sha256(key.encode()).digest()
    x = 0.18 + (h[0] / 255) * 0.64
    y = 0.18 + (h[1] / 255) * 0.64
    return round(x, 4), round(y, 4)


def compute_gaps(db: Session, workspace_id: str, resolved_keys: set[str]) -> list[GapCluster]:
    # Collapse identical questions first (cheap), then embed the distinct ones.
    counts: dict[str, _Item] = {}
    for text, ts in _unanswered_questions(db, workspace_id):
        norm = text.strip()
        if norm in counts:
            it = counts[norm]
            it.count += 1
            it.last_seen = max(it.last_seen, ts)
        else:
            counts[norm] = _Item(text=norm, count=1, last_seen=ts, emb=[])
    if not counts:
        return []

    items = list(counts.values())
    for it in items:
        it.emb = embed_query(it.text)

    # Greedy similarity clustering (small N; deterministic by descending count).
    items.sort(key=lambda i: (-i.count, i.text))
    clusters: list[list[_Item]] = []
    centroids: list[list[float]] = []
    for it in items:
        placed = False
        for ci, cen in enumerate(centroids):
            if _cosine(it.emb, cen) >= _SIM_THRESHOLD:
                clusters[ci].append(it)
                placed = True
                break
        if not placed:
            clusters.append([it])
            centroids.append(it.emb)

    result: list[GapCluster] = []
    for members in clusters:
        total = sum(m.count for m in members)
        rep = max(members, key=lambda m: (m.count, m.last_seen))
        # Stable key: the canonical (lexicographically first) member, so the key
        # survives new occurrences arriving and preserves resolution linkage.
        canonical = min(m.text.lower() for m in members)
        key = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        x, y = _placement(key)
        radius = round(0.12 + min(0.16, (total - 1) * 0.03), 4)
        result.append(
            GapCluster(
                key=key,
                query=rep.text,
                count=total,
                last_seen=max(m.last_seen for m in members),
                x=x,
                y=y,
                radius=radius,
                resolved=key in resolved_keys,
                members=[m.text for m in members],
            )
        )
    result.sort(key=lambda g: (-g.count, g.query))
    return result
