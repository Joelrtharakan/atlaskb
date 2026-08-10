// Small token store backed by localStorage. Kept separate from the auth React
// context so the API client can read/refresh tokens without importing React.

import type { TokenPair } from "./types";

const ACCESS_KEY = "atlaskb.access";
const REFRESH_KEY = "atlaskb.refresh";
const WORKSPACE_KEY = "atlaskb.workspace";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(tokens: TokenPair): void {
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(WORKSPACE_KEY);
  // Tells AuthProvider its in-memory `isAuthenticated` is now stale — this
  // fires from api.ts too (a failed silent refresh on a 401), not just from
  // an explicit logout() call, so the React auth state can't just clear
  // itself inline the way logout() does.
  window.dispatchEvent(new Event("atlaskb-auth-cleared"));
}

/** The active workspace id, sent as X-Workspace-Id on scoped requests. */
export function getActiveWorkspace(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(WORKSPACE_KEY);
}

export function setActiveWorkspace(id: string | null): void {
  if (id) window.localStorage.setItem(WORKSPACE_KEY, id);
  else window.localStorage.removeItem(WORKSPACE_KEY);
}
