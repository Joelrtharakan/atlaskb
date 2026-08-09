"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { AuroraBackground } from "@/components/shell/AuroraBackground";
import { ApiError, api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { useWorkspace } from "@/lib/workspace";

import { Button } from "./Button";
import { ContourProgress } from "./ContourProgress";
import { Field } from "./Field";

const BASE_NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/documents", label: "Documents" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Chat" },
  { href: "/settings", label: "Settings" },
];
const ADMIN_NAV = [
  { href: "/members", label: "Members" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/content-gaps", label: "Content Gaps" },
  { href: "/admin/evals", label: "Evals" },
];

function Loading() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <ContourProgress size={40} label="Loading" />
    </main>
  );
}

/** First-run screen: an authenticated user with no workspace must create one. */
function CreateFirstWorkspace() {
  const { refresh, setActive } = useWorkspace();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setPending(true);
    setError(null);
    try {
      const ws = await api.createWorkspace(name.trim());
      setActive(ws.id);
      await refresh();
      window.location.assign("/documents");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the workspace. Try again.");
      setPending(false);
    }
  }

  return (
    <main className="min-h-screen p-3 sm:p-5">
      <div className="neatline flex min-h-[calc(100vh-1.5rem)] flex-col items-center justify-center sm:min-h-[calc(100vh-2.5rem)]">
        <form onSubmit={onCreate} className="w-full max-w-sm px-6">
          <p className="marginalia mb-3 text-[0.7rem] uppercase tracking-cartouche text-graphite">
            One more step
          </p>
          <h1 className="font-display text-3xl font-medium text-ink">Create your first workspace</h1>
          <p className="mt-2 text-sm text-graphite">
            Documents, members, and chats all live inside a workspace. You&rsquo;ll be its admin.
          </p>
          <div className="mt-6">
            <Field
              label="Workspace name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Research"
              autoFocus
            />
          </div>
          {error ? (
            <p role="alert" className="mt-3 border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={pending || !name.trim()} className="mt-5 w-full">
            {pending ? "Creating…" : "Create workspace"}
          </Button>
        </form>
      </div>
    </main>
  );
}

function WorkspaceSwitcher() {
  const { workspaces, active, setActive } = useWorkspace();

  async function onNew() {
    const name = window.prompt("Name your new workspace");
    if (!name?.trim()) return;
    const ws = await api.createWorkspace(name.trim());
    setActive(ws.id);
    window.location.reload();
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="ws-switcher" className="sr-only">
        Active workspace
      </label>
      <select
        id="ws-switcher"
        value={active?.id ?? ""}
        onChange={(e) => {
          if (e.target.value === "__new__") {
            onNew();
            return;
          }
          setActive(e.target.value);
          window.location.reload();
        }}
        className="max-w-[12rem] truncate border border-graphite/40 bg-linen/60 px-2 py-1 font-mono text-xs text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
      >
        {workspaces.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name} · {w.role}
          </option>
        ))}
        <option value="__new__">+ New workspace…</option>
      </select>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const auth = useRequireAuth();
  const ws = useWorkspace();
  const pathname = usePathname();
  const router = useRouter();

  if (!auth.ready || !auth.isAuthenticated || !ws.ready) return <Loading />;
  if (ws.workspaces.length === 0) return <CreateFirstWorkspace />;

  const nav = ws.role === "admin" ? [...BASE_NAV, ...ADMIN_NAV] : BASE_NAV;

  return (
    <main className="h-screen overflow-hidden p-3 sm:p-5">
      <div className="neatline relative flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        <header className="relative z-10 flex flex-wrap items-center justify-between gap-3 border-b border-brass/20 bg-deep-chart/70 px-4 py-3 backdrop-blur-md sm:px-6">
          <div className="flex items-center gap-6">
            <Link href="/documents" className="flex items-center gap-2">
              <span aria-hidden className="text-pewter">
                ◈
              </span>
              <span className="font-mono text-sm uppercase tracking-cartouche text-ink">AtlasKB</span>
            </Link>
            <nav aria-label="Primary" className="flex flex-wrap items-center gap-1">
              {nav.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={
                      "border-b-2 px-2 py-1 font-mono text-xs uppercase tracking-cartouche " +
                      "transition-colors focus-visible:outline-none focus-visible:ring-2 " +
                      "focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen " +
                      (active
                        ? "border-brass text-parchment"
                        : "border-transparent text-graphite hover:text-parchment")
                    }
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <WorkspaceSwitcher />
            <span className="marginalia hidden text-xs sm:inline">{auth.email}</span>
            <Button
              variant="ghost"
              onClick={() => {
                auth.logout();
                router.replace("/login");
              }}
            >
              Log out
            </Button>
          </div>
        </header>

        <div className="relative z-10 min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </main>
  );
}
