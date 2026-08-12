"""Q&A endpoint: cache → LangGraph agent (RBAC-scoped retrieval) → grounded answer.

Accepts JWT or API-key auth, is tenant/ACL-scoped, rate-limited, and persists the
turn to a tenant-scoped conversation.
"""

from __future__ import annotations

import hashlib
import time

import openai
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, llm
from app.agent import run_agent
from app.cache import cache_get, cache_key, cache_set, get_workspace_epoch
from app.config import settings
from app.conflict_detection import Relationship, detect_conflicts_structured
from app.conflict_detection import persistence as conflict_persistence
from app.db import get_db
from app.deps import get_principal
from app.embeddings import embed_query
from app.llm import CANNOT_ANSWER
from app.logging_config import get_logger
from app.models import Chunk, Conversation, Document, DocumentVersion, Message, MessageFeedback
from app.ratelimit import check_rate_limit
from app.rbac import Principal
from app.retrieval import RetrievedChunk, config_fingerprint, find_relevant_document, hybrid_search
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    Conflict,
    Evidence,
    FeedbackOut,
    FeedbackRequest,
    ScoredChunk,
    TemporalInfo,
    TokenUsageOut,
    VersionDiffEntryOut,
)
from app.temporal import (
    DiffKind,
    TemporalIntent,
    classify_temporal_intent,
    diff_versions,
    resolve_two_versions,
    resolve_version_reference,
    summarize_diff,
)
from app.timing import StageTimer
from app.trust_summary import build_trust_summary

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger(__name__)


def _resolve_conversation(
    db: Session, principal: Principal, conversation_id: str | None, question: str
) -> Conversation:
    if conversation_id:
        convo = db.get(Conversation, conversation_id)
        # 404 for another tenant's/user's conversation — never confirm it exists.
        if (
            convo is None
            or convo.workspace_id != principal.workspace_id
            or convo.user_id != principal.user_id
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
        return convo

    convo = Conversation(
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        title=question[:300],
    )
    db.add(convo)
    db.flush()
    return convo


def _load_history(db: Session, conversation_id: str) -> list[dict]:
    """Prior turns of a conversation, oldest first, as ``{role, content}`` dicts."""
    rows = (
        db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        .scalars()
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in rows]


def _history_sig(history: list[dict]) -> str:
    """Short digest of the conversation so far — folded into the cache key so a
    follow-up like "has that changed?" cannot collide across conversations."""
    if not history:
        return "0"
    joined = "\x1f".join(f"{m['role']}:{m['content']}" for m in history)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _answer_temporal_question(
    db: Session,
    principal: Principal,
    convo: Conversation,
    question: str,
    intent: TemporalIntent,
    timer: StageTimer,
    trust_mode: str = "BALANCED",
) -> ChatResponse:
    """Trust Layer Phase 2: answer a HISTORICAL/VERSION_SPECIFIC/
    COMPARE_VERSIONS/CHANGE_SUMMARY question, grounded in exactly the
    resolved version(s) — never the current version by default. If the
    target document or version can't be resolved, returns an explicit,
    specific refusal (never a silent fall-back to current-version content).
    """

    def _refuse(message: str, temporal: TemporalInfo) -> ChatResponse:
        assistant_message = Message(
            conversation_id=convo.id, workspace_id=principal.workspace_id,
            role="assistant", content=message,
        )
        db.add(assistant_message)
        db.commit()
        log.info(
            "chat.trace", user_id=principal.user_id, cached=False, trust_mode=trust_mode,
            answerable=False, temporal_intent=temporal.intent, stage_durations_ms=timer.as_dict(),
        )
        return ChatResponse(
            answerable=False, answer=message, citations=[], retrieved=[],
            message_id=assistant_message.id, cached=False, conversation_id=convo.id,
            iterations=0, queries=[question], usage=TokenUsageOut(), temporal=temporal,
            trust_mode=trust_mode,
        )

    with timer.stage("temporal_resolution"):
        embedding = None if settings.retrieval_mode == "sparse_only" else embed_query(question)
        document_id = find_relevant_document(db, question, embedding, principal)

    if document_id is None:
        return _refuse(
            "I couldn't identify which document your question is about, so I can't "
            "resolve a specific version of it.",
            TemporalInfo(intent=intent.value),
        )

    versions = list(
        db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id)).all()
    )

    if intent in (TemporalIntent.COMPARE_VERSIONS, TemporalIntent.CHANGE_SUMMARY):
        res_old, res_new = resolve_two_versions(question, versions)
        if res_old.version is None or res_new.version is None:
            reason = res_old.reason or res_new.reason or "I couldn't resolve which versions to compare."
            return _refuse(reason, TemporalInfo(intent=intent.value, document_id=document_id))

        old_chunks = list(
            db.scalars(
                select(Chunk).where(Chunk.version_id == res_old.version.id).order_by(Chunk.chunk_index)
            ).all()
        )
        new_chunks = list(
            db.scalars(
                select(Chunk).where(Chunk.version_id == res_new.version.id).order_by(Chunk.chunk_index)
            ).all()
        )
        entries = diff_versions(old_chunks, new_chunks)
        summary = summarize_diff(
            entries,
            old_label=f"version {res_old.version.version_number}",
            new_label=f"version {res_new.version.version_number}",
        )
        citations = [
            Citation(
                claim=f"{e.kind.value.title()}: section {e.chunk_index}",
                chunk_ids=[cid for cid in (e.old_chunk_id, e.new_chunk_id) if cid],
            )
            for e in entries
            if e.kind != DiffKind.UNCHANGED
        ]

        assistant_message = Message(
            conversation_id=convo.id, workspace_id=principal.workspace_id,
            role="assistant", content=summary,
        )
        db.add(assistant_message)
        db.commit()
        log.info(
            "chat.trace", user_id=principal.user_id, cached=False, trust_mode=trust_mode,
            answerable=True, temporal_intent=intent.value, stage_durations_ms=timer.as_dict(),
        )
        return ChatResponse(
            answerable=True, answer=summary, citations=citations, retrieved=[],
            message_id=assistant_message.id, cached=False, conversation_id=convo.id,
            iterations=0, queries=[question], usage=TokenUsageOut(),
            trust_mode=trust_mode,
            trust_summary=build_trust_summary(
                answerable=True, answer=summary, citations=citations, evidence=[], conflicts=[]
            ),
            temporal=TemporalInfo(
                intent=intent.value,
                document_id=document_id,
                compared_version_numbers=[
                    res_old.version.version_number, res_new.version.version_number
                ],
                diff=[
                    VersionDiffEntryOut(
                        kind=e.kind.value, chunk_index=e.chunk_index,
                        old_chunk_id=e.old_chunk_id, new_chunk_id=e.new_chunk_id,
                        old_text=e.old_text, new_text=e.new_text,
                    )
                    for e in entries
                ],
            ),
        )

    # HISTORICAL or VERSION_SPECIFIC: answer grounded in exactly one version.
    resolution = resolve_version_reference(question, versions)
    if resolution.version is None:
        return _refuse(
            resolution.reason or "I couldn't resolve which version of this document you mean.",
            TemporalInfo(intent=intent.value, document_id=document_id),
        )

    version_chunks = list(
        db.scalars(
            select(Chunk)
            .where(Chunk.version_id == resolution.version.id)
            .order_by(Chunk.chunk_index)
            .limit(settings.rerank_candidate_k)
        ).all()
    )
    if not version_chunks:
        return _refuse(
            f"Version {resolution.version.version_number} of this document has no readable content.",
            TemporalInfo(
                intent=intent.value, document_id=document_id,
                resolved_version_number=resolution.version.version_number,
            ),
        )

    retrieved_chunks = [
        RetrievedChunk(
            chunk_id=c.id, document_id=c.document_id, version_id=c.version_id,
            text=c.text, page_num=c.page_num, section=c.section, score=1.0,
        )
        for c in version_chunks
    ]
    with timer.stage("generation"):
        grounded = llm.generate_answer(question, retrieved_chunks)

    citations = [Citation(**c) for c in grounded.citations] if grounded.answerable else []

    assistant_message = Message(
        conversation_id=convo.id, workspace_id=principal.workspace_id,
        role="assistant", content=grounded.answer,
    )
    db.add(assistant_message)
    db.commit()
    log.info(
        "chat.trace", user_id=principal.user_id, cached=False, trust_mode=trust_mode,
        answerable=grounded.answerable, temporal_intent=intent.value,
        retrieval_count=len(retrieved_chunks), stage_durations_ms=timer.as_dict(),
    )
    return ChatResponse(
        answerable=grounded.answerable,
        answer=grounded.answer,
        citations=citations,
        retrieved=[
            ScoredChunk(
                chunk_id=c.chunk_id, document_id=c.document_id, version_id=c.version_id,
                text=c.text, page_num=c.page_num, section=c.section, score=c.score,
                dense_score=None, sparse_score=None, rerank_score=None,
            )
            for c in retrieved_chunks
        ],
        message_id=assistant_message.id, cached=False, conversation_id=convo.id,
        iterations=1, queries=[question],
        usage=TokenUsageOut(
            prompt=grounded.usage.prompt, completion=grounded.usage.completion, total=grounded.usage.total
        ),
        trust_mode=trust_mode,
        trust_summary=build_trust_summary(
            answerable=grounded.answerable, answer=grounded.answer,
            citations=citations, evidence=[], conflicts=[],
        ),
        temporal=TemporalInfo(
            intent=intent.value, document_id=document_id,
            resolved_version_number=resolution.version.version_number,
        ),
    )


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> ChatResponse:
    _t0 = time.perf_counter()
    timer = StageTimer()
    check_rate_limit(principal)
    convo = _resolve_conversation(db, principal, body.conversation_id, body.question)
    # Prior turns (before this question) drive follow-up reference resolution.
    history = _load_history(db, convo.id)
    db.add(
        Message(
            conversation_id=convo.id,
            workspace_id=principal.workspace_id,
            role="user",
            content=body.question,
        )
    )

    # Trust Layer Phase 2: a historical/version-targeted question is answered
    # on a dedicated path, grounded in exactly the resolved version(s) — never
    # silently substituting the current version. CURRENT/UNKNOWN fall through
    # to the normal cache -> agent path below, unchanged.
    temporal_intent = classify_temporal_intent(body.question)
    if temporal_intent not in (TemporalIntent.CURRENT, TemporalIntent.UNKNOWN):
        with timer.stage("temporal"):
            return _answer_temporal_question(
                db, principal, convo, body.question, temporal_intent, timer, body.trust_mode
            )

    key = cache_key(
        namespace="chat",
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        # Conversation history is part of the key: the same follow-up text means
        # different things in different threads, so answers must not be shared.
        # trust_mode is included too (Trust Layer Phase 4) — FAST/BALANCED/
        # MAX_TRUST run genuinely different work, so they must never share a
        # cached answer.
        model=(
            f"{settings.llm_model}:k{body.top_k}:h{_history_sig(history)}:"
            f"{config_fingerprint()}:tm{body.trust_mode}"
        ),
        query=body.question,
        # Trust Layer Phase 8: bumped on document upload/reupload, ACL
        # change, or membership/role change — makes this key permanently
        # unreachable the moment any of those happen, instead of waiting up
        # to cache_ttl_seconds to stop serving a now-stale answer.
        epoch=get_workspace_epoch(principal.workspace_id),
    )
    with timer.stage("cache"):
        cached = cache_get(key)
    if cached is not None:
        assistant_message = Message(
            conversation_id=convo.id,
            workspace_id=principal.workspace_id,
            role="assistant",
            content=cached["answer"],
        )
        db.add(assistant_message)
        db.commit()
        # Trust Layer Phase 13: one structured trace line per request, with
        # every field the spec asked for (stage durations, model, trust
        # mode, cache hit/miss, final answer status) — never raw document
        # content, only counts/booleans/ids, same discipline the rest of
        # this file's logging already follows.
        log.info(
            "chat.trace",
            user_id=principal.user_id,
            cached=True,
            trust_mode=cached.get("trust_mode", body.trust_mode),
            answerable=cached["answerable"],
            stage_durations_ms=timer.as_dict(),
        )
        cached_citations = [Citation(**c) for c in cached["citations"]]
        cached_evidence = [Evidence(**e) for e in cached.get("evidence", [])]
        cached_conflicts = [Conflict(**c) for c in cached.get("conflicts", [])]
        return ChatResponse(
            answerable=cached["answerable"],
            answer=cached["answer"],
            citations=cached_citations,
            retrieved=[ScoredChunk(**c) for c in cached["retrieved"]],
            conflicts=cached_conflicts,
            evidence=cached_evidence,
            message_id=assistant_message.id,
            cached=True,
            conversation_id=convo.id,
            iterations=cached.get("iterations", 0),
            queries=cached.get("queries", []),
            # A cache hit spends no tokens.
            usage=TokenUsageOut(),
            trust_mode=cached.get("trust_mode", body.trust_mode),
            trust_summary=build_trust_summary(
                answerable=cached["answerable"], answer=cached["answer"],
                citations=cached_citations, evidence=cached_evidence, conflicts=cached_conflicts,
            ),
        )

    def retrieve(query: str):
        # sparse_only mode (T9.0) never needs a vector at all — skip the
        # embedding call entirely rather than computing and discarding one.
        with timer.stage("retrieval"):
            embedding = None if settings.retrieval_mode == "sparse_only" else embed_query(query)
        return hybrid_search(db, query, embedding, principal, top_k=body.top_k, timer=timer)

    # On a follow-up turn, bind the conversation history into the condense
    # (query-rewrite) and generation steps; first turns keep single-turn behavior.
    # Always explicit (never the agent's own un-timed defaults) so every stage
    # shows up in the T9.5 breakdown regardless of whether this is a follow-up.
    def condense(q: str):
        with timer.stage("condense"):
            return llm.condense_query(history, q) if history else (q, llm.TokenUsage())

    def assess(q: str, chunks):
        with timer.stage("assess"):
            return llm.assess_context(q, chunks)

    def generate(q: str, chunks):
        with timer.stage("generation"):
            return llm.generate_answer(q, chunks, history=history) if history else llm.generate_answer(q, chunks)

    try:
        result = run_agent(
            body.question, retrieve, assess_fn=assess, condense_fn=condense, generate_fn=generate
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except openai.APIConnectionError as exc:
        # Can't reach the LLM daemon (e.g. Ollama not running). Give an actionable
        # message without leaking the client stack trace to the API caller.
        log.warning("chat.llm_unreachable", error=str(exc))
        if settings.llm_provider == "ollama":
            detail = (
                f"Ollama is unavailable at {settings.ollama_base_url}. "
                f"Start Ollama and ensure {settings.ollama_model} is installed."
            )
        else:
            detail = "LLM provider is unreachable."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)
    except openai.APIError as exc:
        log.warning("chat.llm_error", error=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM provider error: {exc}")

    grounded = result.answer
    retrieved = [
        ScoredChunk(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            version_id=h.version_id,
            text=h.text,
            page_num=h.page_num,
            section=h.section,
            score=h.score,
            dense_score=h.dense_score,
            sparse_score=h.sparse_score,
            rerank_score=h.rerank_score,
        )
        for h in result.chunks
    ]
    answer = grounded.answer if grounded.answerable else CANNOT_ANSWER
    citations = (
        [Citation(**c) for c in grounded.citations] if grounded.answerable else []
    )

    # Structured conflict-detection pipeline (Trust Layer Phase 1): claim
    # extraction -> candidate filtering -> deterministic-then-LLM relationship
    # classification. Independent of which chunks the answer actually cited.
    # Only worth running when there's an answer to caveat and more than one
    # source in play. Trust Layer Phase 4: FAST skips this stage entirely;
    # MAX_TRUST widens the candidate net (settings.max_trust_* overrides,
    # never a global settings mutation — see conflict_detection/candidates.py).
    conflict_dicts: list[dict] = []
    conflict_usage = llm.TokenUsage()
    # bool(...): Python's `and` returns the last evaluated operand, not a
    # coerced bool — without this, a truthy `result.chunks` would make this
    # variable the chunk list itself, not True. Harmless for the `if
    # run_conflict_detection:` check below (any non-empty list is truthy
    # too), but Phase 13's structured trace logging passes this value
    # straight into a log line — without the coercion, that would leak raw
    # chunk text (real document content) into logs. Caught by
    # test_observability.py, not shipped silently.
    run_conflict_detection = bool(
        settings.conflict_detection_enabled
        and body.trust_mode != "FAST"
        and grounded.answerable
        and result.chunks
    )
    if run_conflict_detection:
        with timer.stage("conflict_detection"):
            candidate_kwargs = (
                {
                    "candidate_min_similarity": settings.max_trust_candidate_min_similarity,
                    "candidate_max_pairs": settings.max_trust_max_candidate_pairs,
                }
                if body.trust_mode == "MAX_TRUST"
                else {}
            )
            structured_conflicts, conflict_usage = detect_conflicts_structured(
                result.chunks, **candidate_kwargs
            )
            # Full audit trail (every relationship, not just contradictions) —
            # best-effort: a persistence failure must never block the answer.
            try:
                conflict_persistence.persist(
                    db, workspace_id=principal.workspace_id, conflicts=structured_conflicts
                )
            except Exception:  # noqa: BLE001
                log.warning("conflict_detection.persist_failed")
            # The chat response's "Sources disagree" signal stays scoped to
            # actual contradictions — SUPPORTS/COMPLEMENTS/UNRELATED/UNCERTAIN
            # pairs are persisted for audit but not surfaced as a conflict here.
            for sc in structured_conflicts:
                if sc.relationship == Relationship.CONTRADICTS:
                    conflict_dicts.append(
                        {
                            "topic": sc.topic,
                            "description": sc.explanation,
                            "chunk_ids": [sc.chunk_id_a, sc.chunk_id_b],
                            "document_ids": sorted({sc.document_id_a, sc.document_id_b}),
                            "relationship": sc.relationship.value,
                            "confidence": sc.confidence,
                            "chunk_id_a": sc.chunk_id_a,
                            "claim_a": sc.claim_a,
                            "chunk_id_b": sc.chunk_id_b,
                            "claim_b": sc.claim_b,
                        }
                    )
    conflicts = [Conflict(**c) for c in conflict_dicts]

    # "Why this answer?" evidence: gather what's already known about each
    # source (retrieval scores + document freshness + version) in one place —
    # raw per-signal facts, not a blended score. FAST/BALANCED cover only
    # actually-cited chunks; MAX_TRUST's "complete evidence trace" covers
    # every retrieved chunk, marking which ones were actually cited via
    # Evidence.is_cited rather than silently mixing the two.
    evidence: list[Evidence] = []
    cited_ids = {cid for c in citations for cid in c.chunk_ids}
    evidence_ids = {c.chunk_id for c in result.chunks} if body.trust_mode == "MAX_TRUST" else cited_ids
    with timer.stage("evidence"):
        if evidence_ids:
            chunk_by_id = {c.chunk_id: c for c in result.chunks}
            evidence_chunks = [chunk_by_id[cid] for cid in evidence_ids if cid in chunk_by_id]
            doc_ids = {c.document_id for c in evidence_chunks}
            version_ids = {c.version_id for c in evidence_chunks if c.version_id}
            docs = {
                d.id: d for d in db.scalars(select(Document).where(Document.id.in_(doc_ids)))
            } if doc_ids else {}
            versions = {
                v.id: v
                for v in db.scalars(select(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
            } if version_ids else {}
            for c in evidence_chunks:
                doc = docs.get(c.document_id)
                ver = versions.get(c.version_id) if c.version_id else None
                evidence.append(
                    Evidence(
                        chunk_id=c.chunk_id,
                        document_id=c.document_id,
                        filename=doc.filename if doc else "",
                        page_num=c.page_num,
                        section=c.section,
                        dense_score=c.dense_score,
                        sparse_score=c.sparse_score,
                        rerank_score=c.rerank_score,
                        staleness=doc.staleness if doc else 0.0,
                        last_verified_at=doc.last_verified_at if doc else None,
                        version_number=ver.version_number if ver else None,
                        is_current_version=ver.is_current_version if ver else True,
                        is_cited=c.chunk_id in cited_ids,
                    )
                )

    assistant_message = Message(
        conversation_id=convo.id,
        workspace_id=principal.workspace_id,
        role="assistant",
        content=answer,
    )
    db.add(assistant_message)
    db.commit()

    total_usage = result.usage + conflict_usage
    usage = TokenUsageOut(
        prompt=total_usage.prompt,
        completion=total_usage.completion,
        total=total_usage.total,
    )

    timing = None
    if settings.expose_timing:
        timing = timer.as_dict()
        auth_ms = getattr(request.state, "auth_ms", None)
        if auth_ms is not None:
            timing["auth"] = round(auth_ms, 1)
        timing["total"] = round((time.perf_counter() - _t0) * 1000, 1)

    payload = ChatResponse(
        answerable=grounded.answerable,
        answer=answer,
        citations=citations,
        retrieved=retrieved,
        conflicts=conflicts,
        evidence=evidence,
        message_id=assistant_message.id,
        cached=False,
        conversation_id=convo.id,
        iterations=result.iterations,
        queries=result.queries,
        usage=usage,
        timing=timing,
        trust_mode=body.trust_mode,
        trust_summary=build_trust_summary(
            answerable=grounded.answerable, answer=answer,
            citations=citations, evidence=evidence, conflicts=conflicts,
        ),
    )
    # Write-through (without the per-request conversation_id / cached flag).
    cache_set(
        key,
        {
            "answerable": payload.answerable,
            "answer": payload.answer,
            "citations": [c.model_dump() for c in payload.citations],
            "retrieved": [r.model_dump() for r in payload.retrieved],
            "conflicts": [c.model_dump() for c in payload.conflicts],
            "evidence": [e.model_dump(mode="json") for e in payload.evidence],
            "iterations": payload.iterations,
            "queries": payload.queries,
            "trust_mode": payload.trust_mode,
        },
    )
    # Trust Layer Phase 13: structured request tracing. One line per request
    # with everything the spec asked for — stage durations, model, retrieval/
    # reranking/conflict-candidate counts, cache hit/miss, trust mode, final
    # answer status — never raw document content, only counts/booleans/ids.
    log.info(
        "chat.trace",
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        answerable=payload.answerable,
        iterations=payload.iterations,
        tokens=usage.total,
        cached=False,
        trust_mode=body.trust_mode,
        model=settings.llm_model,
        retrieval_count=len(result.chunks),
        reranking_enabled=settings.rerank_enabled,
        conflict_detection_ran=run_conflict_detection,
        conflict_candidate_count=len(structured_conflicts) if run_conflict_detection else 0,
        stage_durations_ms=timer.as_dict(),
    )
    return payload


@router.post("/messages/{message_id}/feedback", response_model=FeedbackOut)
def rate_message(
    message_id: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> FeedbackOut:
    """Thumbs up/down an assistant answer. Re-rating overwrites the prior rating
    (upsert on message_id+user_id) rather than accumulating duplicates — this is
    "does this answer look right", not a vote tally. Scoped to the message's own
    conversation owner: you can only rate answers given to you."""
    msg = db.get(Message, message_id)
    if msg is None or msg.workspace_id != principal.workspace_id or msg.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    convo = db.get(Conversation, msg.conversation_id)
    if convo is None or convo.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")

    existing = db.scalar(
        select(MessageFeedback).where(
            MessageFeedback.message_id == message_id,
            MessageFeedback.user_id == principal.user_id,
        )
    )
    if existing is not None:
        existing.rating = body.rating
    else:
        db.add(
            MessageFeedback(
                message_id=message_id,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                rating=body.rating,
            )
        )
    audit.record(
        db, workspace_id=principal.workspace_id, user_id=principal.user_id,
        action="message.feedback", target=message_id, meta={"rating": body.rating},
    )
    db.commit()
    log.info(
        "chat.feedback", user_id=principal.user_id, message_id=message_id, rating=body.rating
    )
    return FeedbackOut(message_id=message_id, rating=body.rating)
