"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["viewer", "editor", "admin"]


# --- Auth ---
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    created_at: datetime


# --- Documents ---
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    content_type: str
    status: str
    source: str | None = "upload"
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    # Freshness signal (display only): when a human last confirmed the doc, and a
    # 0..1 staleness derived from its age. Populated from the ORM property.
    last_verified_at: datetime | None = None
    staleness: float = 0.0


class DocumentDetail(DocumentOut):
    chunk_count: int
    can_manage_access: bool = False


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    content_hash: str | None = None
    source: str | None = None
    created_at: datetime
    created_by: str | None = None
    is_current_version: bool
    chunk_count: int = 0


class DocumentVersionsResponse(BaseModel):
    document_id: str
    versions: list[DocumentVersionOut]


class ChunkSample(BaseModel):
    """One chunk as a stratum of the Core Sample: length drives layer thickness,
    confidence (embedding centrality) + doc staleness drive its color."""

    chunk_id: str
    chunk_index: int
    length: int
    page_num: int | None = None
    section: str | None = None
    preview: str
    confidence: float
    staleness: float


class ChunkSamplesResponse(BaseModel):
    document_id: str
    filename: str
    layers: list[ChunkSample]


class ReliefCell(BaseModel):
    """One document as a cell of the Dashboard relief map. `mass` (chunk count)
    drives peak height; `staleness` pulls it down into a valley."""

    id: str
    filename: str
    status: str
    mass: int
    staleness: float


class ReliefSummary(BaseModel):
    cells: list[ReliefCell]


class ContentGap(BaseModel):
    """An unanswered-question cluster → one fog patch on the Fog-of-War map."""

    key: str
    query: str
    count: int
    x: float
    y: float
    radius: float
    resolved: bool
    members: list[str] = []
    # Trust Layer Phase 7: computed live against current documents/ACLs, not
    # from historical data — see app/content_gaps.py's module docstring.
    cause: str = "UNCLASSIFIED"
    affected_user_ids: list[str] = []
    relevant_document_ids: list[str] = []
    suggested_remediation: str = "Not yet classified."


class ContentGapsResponse(BaseModel):
    gaps: list[ContentGap]


class QueryVolumePoint(BaseModel):
    date: str
    count: int


class QueryVolumeResponse(BaseModel):
    points: list[QueryVolumePoint]


# --- Search ---
class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


class ScoredChunk(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str | None = None
    text: str
    page_num: int | None = None
    section: str | None = None
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[ScoredChunk]
    # True when served from the semantic cache.
    cached: bool = False


# --- Chat ---
class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)
    # Continue an existing conversation (must belong to the caller's tenant).
    conversation_id: str | None = None
    # Trust Layer Phase 4: per-request latency/thoroughness tradeoff.
    #   FAST       -> retrieval + reranking + generation + basic evidence,
    #                 conflict detection skipped entirely.
    #   BALANCED   -> today's default: adds conditional conflict detection
    #                 (already skips itself when there's nothing to compare).
    #   MAX_TRUST  -> conflict detection with a wider candidate net, evidence
    #                 built for every retrieved chunk, not just cited ones.
    # Real per-request behavior, not a T9.0-style env-only ablation flag —
    # folded into the cache key so modes never share a cached answer.
    trust_mode: Literal["FAST", "BALANCED", "MAX_TRUST"] = "BALANCED"


class Citation(BaseModel):
    claim: str
    chunk_ids: list[str]


class TokenUsageOut(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class Conflict(BaseModel):
    """A factual disagreement between chunks from two or more different
    documents — e.g. one source says 14 days, another says 30.

    ``chunk_ids``/``document_ids`` remain the original pointer-only fields
    (back-compat with pre-Phase-1 clients). Trust Layer Phase 1's structured
    pipeline adds ``relationship``/``confidence`` (see
    ``app/conflict_detection/`` — confidence is either a fixed, documented
    deterministic constant or the model's own self-reported value, never
    fabricated) plus the exact claim pair (``chunk_id_a/b``, ``claim_a/b``)
    so a reader isn't just told sources disagree but can see the two
    conflicting statements side by side."""

    topic: str
    description: str
    chunk_ids: list[str]
    document_ids: list[str]
    relationship: str = "CONTRADICTS"
    confidence: float | None = None
    chunk_id_a: str | None = None
    claim_a: str | None = None
    chunk_id_b: str | None = None
    claim_b: str | None = None


class Evidence(BaseModel):
    """Everything already known about one *cited* chunk's source, gathered in one
    place for "Why this answer?" — deliberately raw, per-signal facts (retrieval
    scores, document freshness, version), never blended into a single score."""

    chunk_id: str
    document_id: str
    filename: str
    page_num: int | None = None
    section: str | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    rerank_score: float | None = None
    staleness: float = 0.0
    last_verified_at: datetime | None = None
    version_number: int | None = None
    is_current_version: bool = True
    # True for every entry under FAST/BALANCED (evidence is only ever built
    # for cited chunks there). MAX_TRUST also includes non-cited retrieved
    # chunks for a "complete evidence trace" — this field is how a caller
    # tells the two apart rather than assuming every entry was actually used
    # in the answer.
    is_cited: bool = True


class VersionDiffEntryOut(BaseModel):
    """One aligned chunk-position between two versions — ADDED/REMOVED/
    CHANGED/UNCHANGED/CONFLICTING, always citing the exact chunk id(s) on
    each side (Trust Layer Phase 2: "every result must cite document, exact
    version, exact chunk")."""

    kind: str
    chunk_index: int
    old_chunk_id: str | None = None
    new_chunk_id: str | None = None
    old_text: str | None = None
    new_text: str | None = None


class TemporalInfo(BaseModel):
    """Trust Layer Phase 2: how a temporal/historical question was resolved —
    present whenever the question was routed off the normal current-version
    path, so the caller can always see *why* (which document, which version,
    or which comparison), never just a bare answer with no version context."""

    intent: str
    document_id: str | None = None
    resolved_version_number: int | None = None
    compared_version_numbers: list[int] | None = None
    diff: list[VersionDiffEntryOut] | None = None


class TrustSummary(BaseModel):
    """Trust Layer Phase 5: structured, evidence-derived trust signals —
    never a single fabricated percentage. Every field traces to a real,
    already-computed value (see app/trust_summary.py); a thin answer (few
    citations, no evidence) reads as thin here, not smoothed into a falsely
    reassuring score."""

    # 0..1, sentence-to-claim coverage (same algorithm eval/run_before_after.py
    # uses offline). None only if the answer had no gradable sentences.
    citation_coverage: float | None = None
    citation_quality: str = "Unknown"  # High | Medium | Low | Unknown
    source_freshness: str = "Unknown"  # High | Medium | Low | Unknown
    version: str = "Unknown"  # Current | Historical | Mixed | Unknown
    conflicts_detected: int = 0
    conflicts_summary: str = "None detected"
    evidence_completeness: str = "Unknown"  # High | Medium | Low | Unknown
    # Always "Passed" when present: retrieval is RBAC/ACL-scoped before this
    # summary is ever built, so an unauthorized chunk cannot have reached the
    # answer in the first place — see app/trust_summary.py's docstring.
    permission_check: str = "Passed"


class ChatResponse(BaseModel):
    answerable: bool
    answer: str
    citations: list[Citation] = []
    # The chunks retrieved and passed to the model, so callers can inspect
    # exactly what grounded (or failed to ground) the answer.
    retrieved: list[ScoredChunk] = []
    # Cross-document factual contradictions found among the retrieved chunks —
    # independent of whether the answer itself cited the conflicting chunks.
    conflicts: list[Conflict] = []
    # Per-cited-source evidence (scores, freshness, version) for "Why this answer?".
    evidence: list[Evidence] = []
    # The persisted assistant Message this turn wrote, so the caller can attach
    # feedback (POST /chat/messages/{message_id}/feedback) to the right turn.
    message_id: str | None = None
    # Agent + cache metadata (added in the multi-tenant phase).
    cached: bool = False
    conversation_id: str | None = None
    iterations: int = 0
    queries: list[str] = []
    # Tokens actually spent on this request (0 on a cache hit).
    usage: TokenUsageOut = TokenUsageOut()
    # Per-stage wall-clock breakdown (ms) — only populated when
    # settings.expose_timing is on (eval harness, T9.5). None otherwise.
    timing: dict[str, float] | None = None
    # Present only when the question was classified as historical/version-
    # specific/comparison (Trust Layer Phase 2) — None for an ordinary
    # current-version question.
    temporal: TemporalInfo | None = None
    # Trust Layer Phase 4: the mode actually used to produce this answer
    # (echoes ChatRequest.trust_mode) — always present, never a fake/omitted
    # value, so a client can tell FAST/BALANCED/MAX_TRUST apart at a glance.
    trust_mode: str = "BALANCED"
    # Trust Layer Phase 5: structured trust signals — None only for a
    # refusal (nothing to summarize trust for).
    trust_summary: TrustSummary | None = None


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]


class FeedbackOut(BaseModel):
    message_id: str
    rating: Literal["up", "down"]


# --- Workspaces ---
class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    role: Role
    created_at: datetime


class MemberOut(BaseModel):
    user_id: str
    email: str
    role: Role
    joined_at: datetime


class RoleUpdate(BaseModel):
    role: Role


# --- Invites ---
class InviteRequest(BaseModel):
    email: EmailStr
    role: Role = "viewer"


class InviteOut(BaseModel):
    id: str
    workspace_id: str
    email: str
    role: Role
    token: str
    # Convenience link the frontend can surface / email.
    invite_url: str
    expires_at: datetime
    accepted_at: datetime | None = None


class InviteAcceptOut(BaseModel):
    workspace_id: str
    role: Role


class InvitePreview(BaseModel):
    status: Literal["valid", "expired", "accepted", "invalid"]
    email: str | None = None
    role: Role | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None


# --- API keys ---
class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # A key can be issued at or below the creator's role in the tenant.
    role: Role | None = None


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    role: Role
    lookup: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiKeyCreated(ApiKeyOut):
    # The plaintext key, returned exactly once at creation.
    key: str


# --- Document access grants ---
class AccessGrant(BaseModel):
    grant_type: Literal["role", "user"]
    role_or_user_id: str


class DocumentAccessUpdate(BaseModel):
    # Empty list = visible to all workspace members. Non-empty = restricted to
    # exactly these roles/users (owner and admins always retain access).
    grants: list[AccessGrant] = []


class DocumentAccessOut(BaseModel):
    grants: list[AccessGrant]


# --- Conversations ---
class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    created_at: datetime
    # The requesting user's own feedback on this message, if any — never other
    # users' ratings, since this is "does this look right to you", not a tally.
    feedback: Literal["up", "down"] | None = None
    # The full ChatResponse this assistant message was created from (citations,
    # evidence, trust_summary, conflicts, retrieved chunks) — None for user
    # messages and for assistant messages written before this field existed.
    # Not re-validated as ChatResponse here: it's a frozen historical record,
    # and a future ChatResponse shape change shouldn't break reading old rows.
    response: dict | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


# --- Admin analytics ---
class DailyCount(BaseModel):
    day: str
    count: int


class AnalyticsResponse(BaseModel):
    workspace_id: str
    documents_total: int
    documents_by_status: dict[str, int]
    chunks_total: int
    conversations_total: int
    messages_total: int
    members_total: int
    active_api_keys: int
    cache_entries: int
    questions_last_7_days: list[DailyCount]


# --- Admin audit log ---
class AuditLogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str | None
    action: str
    target: str | None
    meta: dict | None
    created_at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntryOut]
    total: int
    limit: int
    offset: int


# --- Admin feedback ---
class FeedbackSummary(BaseModel):
    message_id: str
    conversation_id: str
    question: str | None
    answer: str
    rating: Literal["up", "down"]
    user_email: str | None
    created_at: datetime


class FeedbackSummaryResponse(BaseModel):
    entries: list[FeedbackSummary]
    up_count: int
    down_count: int


# --- Admin evals headline (Trust Layer T9.8) ---
class EvalHeadline(BaseModel):
    """The complete final metrics picture, assembled entirely from real
    eval/results/*.json files at request time — never a hand-typed number.
    Any field is None if its source file wasn't found, not guessed."""

    total_questions: int | None = None
    answer_accuracy: float | None = None
    retrieval_hit_rate: float | None = None
    citation_accuracy: float | None = None
    citation_coverage: float | None = None
    conflict_detection_accuracy: float | None = None
    refusal_accuracy: float | None = None
    # Must read as exactly 0. None means "not measured", never silently 0.
    permission_leakage: int | None = None
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    cache_hit_rate: float | None = None
    adversarial_passed: int | None = None
    adversarial_total: int | None = None
    prompt_injection_passed: int | None = None
    prompt_injection_total: int | None = None
    # Which files actually contributed, so a missing metric is traceable
    # rather than mysterious.
    source_files: list[str] = []
    missing_files: list[str] = []


# --- Connectors (Trust Layer Phase 11: Google Drive) ---
class ConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    name: str
    status: str
    connected: bool  # whether credentials_ref is present, without ever exposing it
    created_at: datetime
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Optional: restrict sync to one Drive folder id (from the folder's URL).
    # Unset syncs every file the connected Google account can read.
    folder_id: str | None = None


class ConnectorAuthorizeOut(BaseModel):
    authorize_url: str


# --- SSO / OIDC (Trust Layer Phase 11) ---
class OIDCConfigOut(BaseModel):
    enabled: bool


class OIDCExchangeRequest(BaseModel):
    code: str


class OIDCExchangeOut(TokenPair):
    # No /auth/me endpoint exists (see apps/web/lib/auth.tsx) — the frontend
    # caches email client-side at sign-in time the same way password login
    # already does; SSO login needs the same thing handed back explicitly
    # since there was no form field to read it from.
    email: str
