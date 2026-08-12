"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { Field } from "@/components/ui/Field";
import { API_BASE, ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const AuthCompass = dynamic(
  () => import("./AuthCompass").then((m) => m.AuthCompass),
  { ssr: false },
);

type Mode = "login" | "signup";

const COPY: Record<
  Mode,
  { eyebrow: string; title: string; blurb: string; cta: string; altText: string; altHref: string; altLabel: string }
> = {
  login: {
    eyebrow: "Return to the survey",
    title: "Log in to AtlasKB",
    blurb: "Pick up where you left the map.",
    cta: "Log in",
    altText: "New here?",
    altHref: "/signup",
    altLabel: "Create an account",
  },
  signup: {
    eyebrow: "Begin a new survey",
    title: "Create your AtlasKB account",
    blurb: "Upload documents and start charting what your organization knows.",
    cta: "Create account",
    altText: "Already mapping?",
    altHref: "/login",
    altLabel: "Log in",
  },
};

const SSO_ERROR_MESSAGES: Record<string, string> = {
  invalid_state: "The sign-in attempt expired or was tampered with. Try again.",
  sso_failed: "Your identity provider didn't accept the sign-in. Try again.",
  email_not_verified: "Your identity provider hasn't verified your email address, so AtlasKB can't sign you in with it.",
};

export function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode];
  const auth = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(
    () => {
      const code = searchParams.get("error");
      return code ? (SSO_ERROR_MESSAGES[code] ?? "Sign-in failed. Try again.") : null;
    },
  );
  const [pending, setPending] = useState(false);
  const [ssoEnabled, setSsoEnabled] = useState(false);

  useEffect(() => {
    api.oidcConfig().then((c) => setSsoEnabled(c.enabled)).catch(() => setSsoEnabled(false));
  }, []);

  // If a session already exists, skip the form.
  useEffect(() => {
    if (auth.ready && auth.isAuthenticated) router.replace("/documents");
  }, [auth.ready, auth.isAuthenticated, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      if (mode === "signup") {
        await auth.signup(email, password);
      } else {
        await auth.login(email, password);
      }
      router.replace("/documents");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `Couldn't ${mode === "signup" ? "create your account" : "log you in"} — the API didn't respond. Check the backend is running and try again.`,
      );
      setPending(false);
    }
  }

  return (
    <main className="min-h-screen p-3 sm:p-5">
      <div className="neatline flex min-h-[calc(100vh-1.5rem)] flex-col sm:min-h-[calc(100vh-2.5rem)]">
        <header className="flex items-center gap-2 px-6 py-4">
          <span aria-hidden className="text-pewter">
            ◈
          </span>
          <Link
            href="/"
            className="font-mono text-sm uppercase tracking-cartouche text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
          >
            AtlasKB
          </Link>
        </header>

        <div className="flex flex-1 items-center gap-10 px-6 sm:px-10">
          <div className="w-full max-w-sm">
            <p className="marginalia mb-3 text-[0.7rem] uppercase tracking-cartouche text-graphite">
              {copy.eyebrow}
            </p>
            <h1 className="font-display text-3xl font-medium leading-tight text-ink sm:text-4xl">
              {copy.title}
            </h1>
            <p className="mt-3 text-sm text-graphite">{copy.blurb}</p>

            <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-5" noValidate>
              <Field
                label="Email"
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
              <Field
                label="Password"
                type="password"
                name="password"
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                required
                minLength={mode === "signup" ? 8 : undefined}
                hint={mode === "signup" ? "At least 8 characters." : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />

              {error ? (
                <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
                  {error}
                </p>
              ) : null}

              <Button type="submit" disabled={pending} className="w-full">
                {pending ? (
                  <>
                    <ContourProgress size={16} label="Working" />
                    {mode === "signup" ? "Creating…" : "Logging in…"}
                  </>
                ) : (
                  copy.cta
                )}
              </Button>
            </form>

            {ssoEnabled ? (
              <>
                <div className="mt-6 flex items-center gap-3" aria-hidden>
                  <span className="h-px flex-1 bg-graphite/30" />
                  <span className="font-mono text-[0.65rem] uppercase tracking-cartouche text-graphite">or</span>
                  <span className="h-px flex-1 bg-graphite/30" />
                </div>
                <Button
                  variant="outline"
                  className="mt-6 w-full"
                  onClick={() => window.location.assign(`${API_BASE}/auth/oidc/login`)}
                >
                  Continue with SSO →
                </Button>
              </>
            ) : null}

            <p className="mt-6 text-sm text-graphite">
              {copy.altText}{" "}
              <Link
                href={copy.altHref}
                className="border-b border-pewter text-ink hover:text-pewter focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
              >
                {copy.altLabel}
              </Link>
            </p>
          </div>

          {/* Understated compass — larger screens only, never louder than the form. */}
          <div className="hidden h-64 flex-1 items-center justify-center lg:flex" aria-hidden>
            <div className="h-56 w-56">
              <AuthCompass />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
