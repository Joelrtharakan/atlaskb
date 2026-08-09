// Typed client for the AtlasKB API.
//
// Error copy follows the house voice: active verbs, and every message states
// what happened and what to do next — never a generic "Something went wrong".

import {
  clearTokens,
  getAccessToken,
  getActiveWorkspace,
  getRefreshToken,
  setTokens,
} from "./tokens";
import type {
  AccessGrant,
  Analytics,
  ChatResponse,
  ChunkSamplesResponse,
  ContentGapsResponse,
  DocumentAccess,
  DocumentDetail,
  DocumentOut,
  EvalResults,
  LLMHealth,
  Invite,
  InvitePreview,
  Member,
  QueryVolumeResponse,
  ReliefSummary,
  Role,
  SearchResponse,
  TokenPair,
  UserOut,
  Workspace,
} from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Pull a human string out of a FastAPI error body ({detail} or 422 list). */
function detailFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
  }
  return fallback;
}

type RequestOptions = {
  method?: string;
  body?: BodyInit | null;
  headers?: Record<string, string>;
  auth?: boolean;
  // Map of HTTP status -> friendly message for this specific call.
  messages?: Record<number, string>;
  fallbackMessage?: string;
  // Override the active workspace for this call (else the stored one is used).
  workspaceId?: string;
  // Internal: prevents infinite refresh recursion.
  _retried?: boolean;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body = null, auth = true, messages = {}, fallbackMessage } = opts;
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };

  if (auth) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const ws = opts.workspaceId ?? getActiveWorkspace();
    if (ws) headers["X-Workspace-Id"] = ws;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, body, headers });
  } catch {
    throw new ApiError(
      `Can't reach the API at ${API_BASE}. Start the backend (uv run uvicorn app.main:app) and try again.`,
      0,
    );
  }

  // Transparently refresh an expired access token once, then retry.
  if (res.status === 401 && auth && !opts._retried) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, { ...opts, _retried: true });
    }
    clearTokens();
    throw new ApiError(
      messages[401] ?? "Your session expired. Log in again to continue.",
      401,
    );
  }

  if (res.status === 204) return undefined as T;

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    const fallback =
      messages[res.status] ??
      fallbackMessage ??
      `The API returned ${res.status}. Check the backend logs and try again.`;
    throw new ApiError(detailFrom(payload, fallback), res.status);
  }

  return payload as T;
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    });
    if (!res.ok) return false;
    const tokens = (await res.json()) as TokenPair;
    setTokens(tokens);
    return true;
  } catch {
    return false;
  }
}

function jsonBody(data: unknown): RequestOptions {
  return {
    body: JSON.stringify(data),
    headers: { "Content-Type": "application/json" },
  };
}

export const api = {
  async signup(email: string, password: string): Promise<UserOut> {
    return request<UserOut>("/auth/signup", {
      method: "POST",
      auth: false,
      ...jsonBody({ email, password }),
      messages: {
        409: "That email is already registered. Log in instead.",
        422: "Enter a valid email and a password of at least 8 characters.",
      },
    });
  },

  async login(email: string, password: string): Promise<TokenPair> {
    return request<TokenPair>("/auth/login", {
      method: "POST",
      auth: false,
      ...jsonBody({ email, password }),
      messages: {
        401: "That email and password don't match. Check them and try again.",
      },
    });
  },

  async listDocuments(): Promise<DocumentOut[]> {
    return request<DocumentOut[]>("/documents");
  },

  async getDocument(id: string): Promise<DocumentDetail> {
    return request<DocumentDetail>(`/documents/${id}`, {
      messages: { 404: "That document doesn't exist, or it isn't yours." },
    });
  },

  async verifyDocument(id: string): Promise<DocumentDetail> {
    return request<DocumentDetail>(`/documents/${id}/verify`, { method: "POST" });
  },

  /** The document's chunks as Core-Sample strata (length + confidence + staleness). */
  async documentChunks(id: string): Promise<ChunkSamplesResponse> {
    return request<ChunkSamplesResponse>(`/documents/${id}/chunks`);
  },

  /** Relief-map data for the Dashboard: every visible doc's mass + staleness. */
  async relief(): Promise<ReliefSummary> {
    return request<ReliefSummary>("/dashboard/relief");
  },

  /** Content-gap clusters (admin) → Fog-of-War patches. */
  async contentGaps(): Promise<ContentGapsResponse> {
    return request<ContentGapsResponse>("/admin/content-gaps");
  },

  /** Mark a gap resolved; returns the updated gap set (that patch cleared). */
  async resolveGap(key: string): Promise<ContentGapsResponse> {
    return request<ContentGapsResponse>(`/admin/content-gaps/${key}/resolve`, {
      method: "POST",
    });
  },

  /** Daily query volume (admin) → drives the Trade Winds flow. */
  async queryVolume(days = 14): Promise<QueryVolumeResponse> {
    return request<QueryVolumeResponse>(`/admin/query-volume?days=${days}`);
  },

  /** Current LLM provider/model + reachability (for the Settings readout). */
  async llmHealth(): Promise<LLMHealth> {
    return request<LLMHealth>("/health/llm");
  },

  async uploadDocument(file: File): Promise<DocumentOut> {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentOut>("/documents", {
      method: "POST",
      body: form,
      messages: {
        415: "AtlasKB reads PDF, Markdown, and HTML. Convert this file and upload it again.",
        413: "That file is too large to upload. Split it into smaller documents.",
      },
    });
  },

  async search(query: string, topK = 8): Promise<SearchResponse> {
    return request<SearchResponse>("/search", {
      method: "POST",
      ...jsonBody({ query, top_k: topK }),
    });
  },

  async chat(question: string, topK = 8): Promise<ChatResponse> {
    return request<ChatResponse>("/chat", {
      method: "POST",
      ...jsonBody({ question, top_k: topK }),
      messages: {
        503: "The answer service isn't configured. Set OPENROUTER_API_KEY on the backend and retry.",
        502: "The answer service failed upstream. Wait a moment and ask again.",
      },
    });
  },

  async analytics(): Promise<Analytics> {
    return request<Analytics>("/admin/analytics", {
      messages: { 403: "Analytics is available to workspace admins only." },
    });
  },

  async evals(): Promise<EvalResults> {
    return request<EvalResults>("/admin/evals", {
      messages: { 403: "Evaluation results are available to workspace admins only." },
    });
  },

  // --- Workspaces ---
  async listWorkspaces(): Promise<Workspace[]> {
    return request<Workspace[]>("/workspaces");
  },

  async createWorkspace(name: string): Promise<Workspace> {
    return request<Workspace>("/workspaces", { method: "POST", ...jsonBody({ name }) });
  },

  async listMembers(workspaceId: string): Promise<Member[]> {
    return request<Member[]>(`/workspaces/${workspaceId}/members`, { workspaceId });
  },

  async invite(workspaceId: string, email: string, role: Role): Promise<Invite> {
    return request<Invite>(`/workspaces/${workspaceId}/invites`, {
      method: "POST",
      workspaceId,
      ...jsonBody({ email, role }),
      messages: {
        403: "Only workspace admins can invite members.",
        409: "That person is already a member of this workspace.",
      },
    });
  },

  async changeRole(workspaceId: string, userId: string, role: Role): Promise<Member> {
    return request<Member>(`/workspaces/${workspaceId}/members/${userId}`, {
      method: "PATCH",
      workspaceId,
      ...jsonBody({ role }),
      messages: { 403: "Only workspace admins can change roles." },
    });
  },

  async removeMember(workspaceId: string, userId: string): Promise<void> {
    return request<void>(`/workspaces/${workspaceId}/members/${userId}`, {
      method: "DELETE",
      workspaceId,
      messages: { 403: "Only workspace admins can remove members." },
    });
  },

  async getInvite(token: string): Promise<InvitePreview> {
    return request<InvitePreview>(`/invites/${token}`, { auth: false });
  },

  async acceptInvite(token: string): Promise<{ workspace_id: string; role: Role }> {
    return request<{ workspace_id: string; role: Role }>(`/invites/${token}/accept`, {
      method: "POST",
      messages: {
        403: "This invite was issued to a different email address. Log in as the invited user.",
        404: "This invite link is not valid.",
        409: "This invite has already been used.",
        410: "This invite has expired. Ask an admin for a new one.",
      },
    });
  },

  // --- Document access ---
  async getDocumentAccess(documentId: string): Promise<DocumentAccess> {
    return request<DocumentAccess>(`/documents/${documentId}/access`);
  },

  async setDocumentAccess(documentId: string, grants: AccessGrant[]): Promise<DocumentAccess> {
    return request<DocumentAccess>(`/documents/${documentId}/access`, {
      method: "PATCH",
      ...jsonBody({ grants }),
    });
  },
};
