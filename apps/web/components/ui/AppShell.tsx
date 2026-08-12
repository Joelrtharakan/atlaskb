"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { AuroraBackground } from "@/components/shell/AuroraBackground";
import { ApiError, api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { useWorkspace } from "@/lib/workspace";

import { Button } from "./Button";
import { ContourProgress } from "./ContourProgress";
import { Field } from "./Field";
import { NewWorkspaceModal } from "./NewWorkspaceModal";

const CORE_NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/documents", label: "Documents" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Chat" },
];
const ADMIN_NAV = [
  { href: "/members", label: "Members" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/content-gaps", label: "Content Gaps" },
  { href: "/admin/evals", label: "Evals" },
  { href: "/admin/feedback", label: "Feedback" },
  { href: "/admin/audit-log", label: "Audit Log" },
  { href: "/admin/connectors", label: "Connectors" },
];
/** Always last — after the admin links when present, so Settings reads as
 *  "the one link that isn't part of the primary or admin workflow." */
const SETTINGS_NAV = { href: "/settings", label: "Settings" };

function Loading() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <ContourProgress size={40} label="Loading" />
    </main>
  );
}

/** Distinct from CreateFirstWorkspace: this is "we couldn't tell whether you
 *  have workspaces" (a failed fetch), not "you confirmed have zero" — showing
 *  the create-workspace form here would silently offer to create a duplicate
 *  workspace for an account that already has one. */
function WorkspaceLoadError({ message }: { message: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-3 sm:p-5">
      <div className="max-w-sm text-center">
        <p className="font-display text-2xl font-medium text-ink">Couldn&rsquo;t load your workspaces</p>
        <p className="mt-2 text-sm text-graphite">{message}</p>
        <Button className="mt-5" onClick={() => window.location.reload()}>
          Try again
        </Button>
      </div>
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
  const [modalOpen, setModalOpen] = useState(false);

  async function onCreate(name: string) {
    const ws = await api.createWorkspace(name);
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
            setModalOpen(true);
            return;
          }
          setActive(e.target.value);
          window.location.reload();
        }}
        className="max-w-[7rem] shrink-0 truncate border border-graphite/40 bg-linen/60 px-2 py-1 font-mono text-xs text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
      >
        {workspaces.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name} · {w.role}
          </option>
        ))}
        <option value="__new__">+ New workspace…</option>
      </select>
      <NewWorkspaceModal open={modalOpen} onClose={() => setModalOpen(false)} onCreate={onCreate} />
    </div>
  );
}

/** Collapses the 6 admin-only links into one dropdown instead of 6 more
 * items in the already-crowded primary nav — with core + admin + settings
 * all as flat links, the nav ran out of room on ordinary window widths and
 * the last couple of links (previously Settings, then Audit Log) silently
 * clipped rather than wrapped, reading as broken/overlapping. */
function AdminMenu({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const active = ADMIN_NAV.some((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      const target = e.target as Node;
      // The menu is portaled to <body> (see below), so it's outside `ref`
      // in the DOM tree even while open — check both, or every mousedown
      // on a menu item would look "outside" and close the menu before its
      // own onClick/navigation had a chance to run.
      if (ref.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => {
          // The nav this button lives in scrolls horizontally
          // (overflow-x-auto), which per the CSS spec forces its
          // overflow-y to clip too — an `absolute` dropdown here would be
          // invisibly cut off. `position: fixed`, positioned from the
          // button's real screen coordinates, sidesteps that entirely.
          const rect = buttonRef.current?.getBoundingClientRect();
          if (rect) setMenuPos({ top: rect.bottom + 4, left: rect.left });
          setOpen((o) => !o);
        }}
        aria-expanded={open}
        aria-haspopup="menu"
        className={
          "shrink-0 border-b-2 px-2 py-1 font-mono text-xs uppercase tracking-cartouche " +
          "transition-colors focus-visible:outline-none focus-visible:ring-2 " +
          "focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen " +
          (active
            ? "border-brass text-parchment"
            : "border-transparent text-graphite hover:text-parchment")
        }
      >
        Admin {open ? "▴" : "▾"}
      </button>
      {open && menuPos
        ? createPortal(
            // Portaled straight to <body>: the header's `backdrop-blur-md`
            // establishes a CSS stacking context (backdrop-filter behaves
            // like `transform` here), which traps any `position: fixed`
            // descendant inside it regardless of z-index — the page content
            // below (a later, sibling stacking context) would otherwise
            // paint over the menu and swallow its clicks. A portal escapes
            // that ancestor entirely instead of trying to out-rank it.
            <div
              ref={menuRef}
              role="menu"
              style={{ top: menuPos.top, left: menuPos.left }}
              className="fixed z-50 min-w-[10rem] border border-graphite/30 bg-deep-chart/95 py-1 shadow-lg backdrop-blur-md"
            >
              {ADMIN_NAV.map((item) => {
                const itemActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    role="menuitem"
                    onClick={() => setOpen(false)}
                    className={
                      "block px-3 py-1.5 font-mono text-xs uppercase tracking-cartouche transition-colors " +
                      (itemActive ? "text-parchment" : "text-graphite hover:text-parchment")
                    }
                  >
                    {item.label}
                  </Link>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

function NavLink({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={
        "shrink-0 border-b-2 px-2 py-1 font-mono text-xs uppercase tracking-cartouche " +
        "transition-colors focus-visible:outline-none focus-visible:ring-2 " +
        "focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen " +
        (active
          ? "border-brass text-parchment"
          : "border-transparent text-graphite hover:text-parchment")
      }
    >
      {label}
    </Link>
  );
}

/** Initials badge standing in for the full email — the email is still
 *  available via the tooltip and to screen readers, it just no longer
 *  duplicates the workspace switcher's own label at full width. */
function UserBadge({ email }: { email: string }) {
  const initials = email.slice(0, 2).toUpperCase();
  return (
    <span
      title={email}
      aria-label={email}
      className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-graphite/40 bg-linen/60 font-mono text-[0.65rem] text-ink"
    >
      {initials}
    </span>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const auth = useRequireAuth();
  const ws = useWorkspace();
  const pathname = usePathname();
  const router = useRouter();

  if (!auth.ready || !auth.isAuthenticated || !ws.ready) return <Loading />;
  if (ws.workspaces.length === 0 && ws.loadError) return <WorkspaceLoadError message={ws.loadError} />;
  if (ws.workspaces.length === 0) return <CreateFirstWorkspace />;

  const isAdmin = ws.role === "admin";

  return (
    <main className="h-screen overflow-hidden p-3 sm:p-5">
      <div className="neatline relative flex h-full flex-col overflow-hidden">
        <AuroraBackground />
        <header className="relative z-10 flex items-center gap-3 border-b border-brass/20 bg-deep-chart/70 px-4 py-2.5 backdrop-blur-md sm:px-6">
          <Link href="/documents" className="flex shrink-0 items-center gap-2">
            <span aria-hidden className="text-pewter">
              ◈
            </span>
            <span className="font-mono text-sm uppercase tracking-cartouche text-ink">AtlasKB</span>
          </Link>
          {/* Scrolls horizontally instead of wrapping if it ever runs out of
              room — the header always stays a single line. Grouped into
              core workflow / admin, each set off by a divider. Settings
              deliberately lives in the fixed right-hand cluster below, not
              in this scrollable region — with 10+ links (core + all admin
              links) it was the item most likely to run out of room and get
              clipped right where the workspace switcher begins, reading as
              an overlap even though it was really an overflow cutoff. */}
          <nav aria-label="Primary" className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
            {CORE_NAV.map((item) => (
              <NavLink
                key={item.href}
                href={item.href}
                label={item.label}
                active={pathname === item.href || pathname.startsWith(`${item.href}/`)}
              />
            ))}
            {isAdmin ? (
              <>
                <span aria-hidden className="mx-1 h-4 w-px shrink-0 bg-graphite/30" />
                <AdminMenu pathname={pathname} />
              </>
            ) : null}
          </nav>
          <div className="flex shrink-0 items-center gap-2.5">
            <NavLink
              href={SETTINGS_NAV.href}
              label={SETTINGS_NAV.label}
              active={pathname === SETTINGS_NAV.href || pathname.startsWith(`${SETTINGS_NAV.href}/`)}
            />
            <span aria-hidden className="h-4 w-px bg-graphite/30" />
            <WorkspaceSwitcher />
            <span aria-hidden className="h-4 w-px bg-graphite/30" />
            {auth.email ? <UserBadge email={auth.email} /> : null}
            <Button
              variant="ghost"
              className="px-2 py-1 text-[0.7rem]"
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
