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


class DocumentDetail(DocumentOut):
    chunk_count: int
    # Whether the caller may edit this document's access scope.
    can_manage_access: bool = False


# --- Search ---
class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


class ScoredChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    page_num: int | None = None
    section: str | None = None
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None


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


class Citation(BaseModel):
    claim: str
    chunk_ids: list[str]


class TokenUsageOut(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class ChatResponse(BaseModel):
    answerable: bool
    answer: str
    citations: list[Citation] = []
    # The chunks retrieved and passed to the model, so callers can inspect
    # exactly what grounded (or failed to ground) the answer.
    retrieved: list[ScoredChunk] = []
    # Agent + cache metadata (added in the multi-tenant phase).
    cached: bool = False
    conversation_id: str | None = None
    iterations: int = 0
    queries: list[str] = []
    # Tokens actually spent on this request (0 on a cache hit).
    usage: TokenUsageOut = TokenUsageOut()


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
    role: str
    content: str
    created_at: datetime


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
