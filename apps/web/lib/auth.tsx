"use client";

// Auth context: holds the current session (email + tokens in localStorage) and
// exposes login/signup/logout. There is no /me endpoint yet, so the email is
// remembered client-side at sign-in time.

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "./api";
import { clearTokens, getAccessToken, setTokens } from "./tokens";

const EMAIL_KEY = "atlaskb.email";

type AuthState = {
  email: string | null;
  isAuthenticated: boolean;
  // False until the first client-side read of localStorage completes.
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (getAccessToken()) {
      setEmail(window.localStorage.getItem(EMAIL_KEY));
    }
    setReady(true);
  }, []);

  // clearTokens() can run outside this component (api.ts clears tokens when
  // a 401's silent refresh also fails) — without this, `email` stays set to
  // whatever it was at mount and `isAuthenticated` never notices the session
  // died, so /login's "already signed in, skip the form" redirect fires on a
  // dead session and bounces the user straight past the login form.
  useEffect(() => {
    const onAuthCleared = () => {
      setEmail(null);
      window.localStorage.removeItem(EMAIL_KEY);
    };
    window.addEventListener("atlaskb-auth-cleared", onAuthCleared);
    return () => window.removeEventListener("atlaskb-auth-cleared", onAuthCleared);
  }, []);

  const login = useCallback(async (emailArg: string, password: string) => {
    const tokens = await api.login(emailArg, password);
    setTokens(tokens);
    window.localStorage.setItem(EMAIL_KEY, emailArg);
    setEmail(emailArg);
  }, []);

  const signup = useCallback(
    async (emailArg: string, password: string) => {
      await api.signup(emailArg, password);
      // Sign the new user straight in.
      await login(emailArg, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    clearTokens();
    window.localStorage.removeItem(EMAIL_KEY);
    setEmail(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ email, isAuthenticated: email !== null, ready, login, signup, logout }),
    [email, ready, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

/** Redirect to /login once we know (client-side) there is no session. */
export function useRequireAuth(): AuthState {
  const auth = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (auth.ready && !auth.isAuthenticated) {
      router.replace("/login");
    }
  }, [auth.ready, auth.isAuthenticated, router]);
  return auth;
}
