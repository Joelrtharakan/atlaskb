"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ContourProgress } from "@/components/ui/ContourProgress";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function OIDCCallback() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const [error, setError] = useState<string | null>(null);
  // React 18 StrictMode double-invokes effects in dev, which would burn
  // the single-use exchange code twice and surface a spurious failure on
  // the (harmless) second call — guard so only the first actually fires.
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current) return;
    exchanged.current = true;

    const code = searchParams.get("code");
    if (!code) {
      router.replace("/login?error=invalid_state");
      return;
    }
    // Exchange the one-time code the backend redirect handed us for a real
    // session — the code itself is never a usable token (see
    // app/routers/oidc.py's exchange endpoint), so a leaked URL alone
    // can't be replayed after this runs once.
    api
      .oidcExchange(code)
      .then(({ access_token, refresh_token, token_type, email }) => {
        auth.loginWithTokens({ access_token, refresh_token, token_type }, email);
        router.replace("/documents");
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Sign-in failed. Try again.");
      });
    // Runs once on mount only — the code is single-use, re-running this on
    // a dependency change would burn it a second time and always fail.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center p-3 sm:p-5">
        <div className="max-w-sm text-center">
          <p className="font-display text-2xl font-medium text-ink">Sign-in failed</p>
          <p className="mt-2 text-sm text-graphite">{error}</p>
          <a
            href="/login"
            className="mt-5 inline-block border-b border-pewter text-sm text-ink hover:text-pewter"
          >
            Back to login
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center">
      <ContourProgress size={40} label="Completing sign-in" />
    </main>
  );
}
