"""Content-gap detection for the Fog-of-War admin view (Trust Layer Phase 7
adds cause classification on top of the original clustering).

A "gap" is a question the assistant could not answer from the documents. We find
those turns (assistant reply == the CANNOT_ANSWER sentinel), take the user
question that prompted each, and cluster near-duplicate questions by embedding
similarity so a repeated blind-spot shows as one thicker patch of fog rather than
many. Gaps are derived on the fly; only resolution state is persisted.

Cause classification is deliberately computed LIVE (re-running retrieval right
now against the workspace's current documents/ACLs), not from a historical
snapshot of what happened at the time each occurrence was asked. This is a
real design choice, not an oversight: nothing about which chunks were
actually retrieved for a past turn is persisted anywhere (Message only
stores role/content), so a historical reconstruction isn't available without
a schema change this phase didn't need — and for an admin deciding what to
fix *right now*, "is this still a gap today" is the more useful question
than "what exactly happened three weeks ago" anyway. The tradeoff: if a
one-off historical failure has since resolved itself (a document was added,
a bug was fixed), live classification will correctly stop flagging it as a
problem rather than keep citing stale history.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.conflict_detection.candidates import select_candidates
from app.conflict_detection.deterministic import try_classify as try_classify_conflict
from app.conflict_detection.signals import extract_dates, extract_entities, extract_numbers
from app.conflict_detection.types import Claim, Relationship
from app.embeddings import embed_query
from app.llm import CANNOT_ANSWER
from app.models import ROLE_ADMIN, Document, Message, WorkspaceMembership
from app.rbac import Principal
from app.retrieval import hybrid_search

# Cosine similarity at/above which two questions are treated as the same gap.
_SIM_THRESHOLD = 0.72
# Cap work per request — plenty for an admin view, bounds embedding cost.
_MAX_TURNS = 200
# Cause classification re-runs live retrieval (admin view + one pass per
# affected user) — bounded to the N most frequent gaps so a workspace with a
# long fog-of-war tail doesn't turn one admin page load into hundreds of
# extra retrieval calls.
_MAX_CLASSIFIED = 20


class GapCause(str, Enum):
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    OUTDATED_DOCUMENT = "OUTDATED_DOCUMENT"
    CONFLICTING_DOCUMENT = "CONFLICTING_DOCUMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    PERMISSION_RESTRICTION = "PERMISSION_RESTRICTION"
    MODEL_FAILURE = "MODEL_FAILURE"
    AMBIGUOUS_QUERY = "AMBIGUOUS_QUERY"
    UNCLASSIFIED = "UNCLASSIFIED"  # beyond _MAX_CLASSIFIED, or classification itself failed


@dataclass
class _Item:
    text: str
    count: int
    last_seen: datetime
    emb: list[float]
    conversation_ids: set[str] = field(default_factory=set)


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
    # Trust Layer Phase 7 additions — see module docstring for why these are
    # computed live rather than from historical data.
    cause: str = GapCause.UNCLASSIFIED.value
    affected_user_ids: list[str] = field(default_factory=list)
    relevant_document_ids: list[str] = field(default_factory=list)
    suggested_remediation: str = "Not yet classified."


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _unanswered_questions(db: Session, workspace_id: str) -> list[tuple[str, datetime, str]]:
    """(question, timestamp, conversation_id) for each turn the assistant
    couldn't answer. conversation_id lets a gap be traced back to the real
    asking user(s) via Conversation.user_id (Trust Layer Phase 7)."""
    rows = db.execute(
        select(Message.conversation_id, Message.role, Message.content, Message.created_at)
        .where(Message.workspace_id == workspace_id)
        .order_by(Message.conversation_id, Message.created_at, Message.id)
    ).all()
    out: list[tuple[str, datetime, str]] = []
    prev: dict[str, tuple[str, str, datetime]] = {}
    for conv, role, content, created in rows:
        if role == "assistant" and content.strip() == CANNOT_ANSWER:
            p = prev.get(conv)
            if p and p[0] == "user" and p[1].strip():
                out.append((p[1].strip(), p[2], conv))
        prev[conv] = (role, content, created)
    return out[-_MAX_TURNS:]


def _placement(key: str) -> tuple[float, float]:
    """Deterministic (x,y) in the interior of the map from the gap key, so a
    given gap always fogs the same region."""
    h = hashlib.sha256(key.encode()).digest()
    x = 0.18 + (h[0] / 255) * 0.64
    y = 0.18 + (h[1] / 255) * 0.64
    return round(x, 4), round(y, 4)


def compute_gaps(
    db: Session, workspace_id: str, resolved_keys: set[str], *, classify: bool = True
) -> list[GapCluster]:
    """``classify=False`` skips live cause classification (Trust Layer
    Phase 7) — used by tests/callers that only need the clustering itself,
    since classification costs real retrieval calls per gap."""
    # Collapse identical questions first (cheap), then embed the distinct ones.
    counts: dict[str, _Item] = {}
    for text, ts, conv in _unanswered_questions(db, workspace_id):
        norm = text.strip()
        if norm in counts:
            it = counts[norm]
            it.count += 1
            it.last_seen = max(it.last_seen, ts)
            it.conversation_ids.add(conv)
        else:
            counts[norm] = _Item(text=norm, count=1, last_seen=ts, emb=[], conversation_ids={conv})
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
        conversation_ids: set[str] = set()
        for m in members:
            conversation_ids |= m.conversation_ids
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
                affected_user_ids=_affected_user_ids(db, conversation_ids),
            )
        )
    result.sort(key=lambda g: (-g.count, g.query))

    if classify:
        for gap in result[:_MAX_CLASSIFIED]:
            _classify_gap(db, workspace_id, gap)

    return result


def _affected_user_ids(db: Session, conversation_ids: set[str]) -> list[str]:
    if not conversation_ids:
        return []
    from app.models import Conversation

    rows = db.scalars(
        select(Conversation.user_id).where(Conversation.id.in_(conversation_ids)).distinct()
    ).all()
    return sorted(rows)


_ADMIN_CLASSIFIER_USER_ID = "content-gap-classifier"


def _has_deterministic_conflict(hits) -> bool:
    """Cheap, no-LLM conflict check for gap classification specifically —
    reuses Phase 1's deterministic numeric/date classifier directly, but
    deliberately skips claim extraction and LLM relationship classification.

    This is a real perf fix, not a shortcut taken lightly: classification
    runs on every admin page load (unlike /chat's conflict pipeline, which
    runs once per real question), and the full LLM pipeline was measured
    live to take 60-85 seconds to classify a handful of gaps against a
    workspace with real document history — unacceptable for a page load.
    The tradeoff is real: this misses subtler conflicts an LLM classifier
    would catch (paraphrased contradictions with no shared numbers/dates),
    same limitation documented in eval/conflicts/README.md for the
    deterministic stage generally. Good enough for "is this topic worth an
    admin's attention," not a substitute for the real pipeline in /chat.
    """
    claims = [
        Claim(
            chunk_id=h.chunk_id, document_id=h.document_id, version_id=h.version_id, text=h.text,
            numbers=extract_numbers(h.text), dates=extract_dates(h.text), entities=extract_entities(h.text),
        )
        for h in hits
    ]
    for candidate in select_candidates(claims):
        result = try_classify_conflict(candidate)
        if result is not None and result.relationship == Relationship.CONTRADICTS:
            return True
    return False


def _classify_gap(db: Session, workspace_id: str, gap: GapCluster) -> None:
    """Mutates ``gap`` in place with cause/relevant_document_ids/
    suggested_remediation. Never raises — a classification failure leaves
    the gap as UNCLASSIFIED rather than breaking the whole admin page."""
    try:
        _classify_gap_inner(db, workspace_id, gap)
    except Exception:  # noqa: BLE001 - a broken classification must not break the dashboard
        gap.cause = GapCause.UNCLASSIFIED.value
        gap.suggested_remediation = "Classification failed — see server logs."


def _classify_gap_inner(db: Session, workspace_id: str, gap: GapCluster) -> None:
    query = gap.query

    # Heuristic, documented as such: a very short question ("the policy?",
    # "tell me") has too little signal to route deterministically — most
    # likely the model's own read on it (a plain refusal) is the correct
    # behavior, not a corpus gap.
    if len(query.split()) <= 3:
        gap.cause = GapCause.AMBIGUOUS_QUERY.value
        gap.suggested_remediation = (
            "This question is too vague to route automatically — no action needed "
            "unless it keeps recurring with more specific phrasing."
        )
        return

    embedding = embed_query(query)
    admin_principal = Principal(
        user_id=_ADMIN_CLASSIFIER_USER_ID, workspace_id=workspace_id, role=ROLE_ADMIN, auth="api_key"
    )
    admin_hits = hybrid_search(db, query, embedding, admin_principal, top_k=5)

    if not admin_hits:
        gap.cause = GapCause.MISSING_DOCUMENT.value
        gap.suggested_remediation = "Upload a document covering this topic — nothing in the corpus is even topically close."
        return

    doc_ids = sorted({h.document_id for h in admin_hits})
    gap.relevant_document_ids = doc_ids
    docs = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(doc_ids)))}

    # Permission check: could every actual asking user see what an
    # unrestricted admin view finds? Real per-user retrieval, not a guess.
    restricted_for: list[str] = []
    for uid in gap.affected_user_ids:
        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.user_id == uid
            )
        )
        if membership is None:
            continue
        user_principal = Principal(user_id=uid, workspace_id=workspace_id, role=membership.role, auth="jwt")
        user_hits = hybrid_search(db, query, embedding, user_principal, top_k=5)
        user_doc_ids = {h.document_id for h in user_hits}
        if set(doc_ids) - user_doc_ids:
            restricted_for.append(uid)
    if restricted_for:
        gap.cause = GapCause.PERMISSION_RESTRICTION.value
        gap.suggested_remediation = (
            "Relevant content exists but is ACL-restricted for at least one asking user — "
            "grant access if that was unintentional, or confirm the restriction is correct."
        )
        return

    doc_names = [docs[d].filename for d in doc_ids if d in docs]
    avg_staleness = (
        sum(docs[d].staleness for d in doc_ids if d in docs) / len(doc_ids) if doc_ids else 0.0
    )
    if avg_staleness > settings.content_gap_staleness_threshold:
        gap.cause = GapCause.OUTDATED_DOCUMENT.value
        gap.suggested_remediation = f"Re-verify or update the stale source(s): {', '.join(doc_names)}."
        return

    if _has_deterministic_conflict(admin_hits):
        gap.cause = GapCause.CONFLICTING_DOCUMENT.value
        gap.suggested_remediation = (
            f"Sources disagree on this topic ({', '.join(doc_names)}) — resolve the conflict "
            "or mark one source as superseded."
        )
        return

    top_score = admin_hits[0].rerank_score
    if top_score is not None and top_score < settings.content_gap_weak_evidence_rerank_threshold:
        gap.cause = GapCause.INSUFFICIENT_EVIDENCE.value
        gap.suggested_remediation = (
            f"The closest match ({doc_names[0] if doc_names else 'unknown source'}) wasn't a "
            "strong enough fit — consider adding more detail to the relevant document."
        )
        return

    # Current, non-conflicting, reasonably-scored content exists and is
    # visible to everyone who asked — yet the historical answer(s) still
    # failed. Distinguishing "retrieval didn't surface it that one time" from
    # "generation keeps failing on it" isn't directly measurable without
    # historical retrieval data (not persisted — see module docstring), so
    # this uses occurrence count as the deciding signal: a one-off is more
    # likely a transient retrieval fluke, a repeated failure with strong
    # evidence available each time points at generation. Documented as a
    # heuristic, not a measured distinction.
    if gap.count <= 2:
        gap.cause = GapCause.RETRIEVAL_FAILURE.value
        gap.suggested_remediation = (
            "Relevant, current content exists now but wasn't surfaced when this was asked — "
            "may have been transient (corpus has changed since). Re-ask to confirm it's fixed."
        )
    else:
        gap.cause = GapCause.MODEL_FAILURE.value
        gap.suggested_remediation = (
            f"Strong evidence exists ({', '.join(doc_names)}) but generation still failed, "
            "repeatedly — investigate the generation step or that document's formatting."
        )
