"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useRequireAuth } from "@/lib/auth";

import { Button } from "./Button";
import { ContourProgress } from "./ContourProgress";

const NAV = [
  { href: "/documents", label: "Documents" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Chat" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/evals", label: "Evals" },
];

// The in-app frame: a map-sheet neatline, a title block header with the survey
// nav, and the current session. Guards its children behind auth.
export function AppShell({ children }: { children: ReactNode }) {
  const auth = useRequireAuth();
  const pathname = usePathname();
  const router = useRouter();

  if (!auth.ready || !auth.isAuthenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <ContourProgress size={40} label="Loading your atlas" />
      </main>
    );
  }

  return (
    <main className="min-h-screen p-3 sm:p-5">
      <div className="neatline flex min-h-[calc(100vh-1.5rem)] flex-col sm:min-h-[calc(100vh-2.5rem)]">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-graphite/25 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-6">
            <Link href="/documents" className="flex items-center gap-2">
              <span aria-hidden className="text-pewter">
                ◈
              </span>
              <span className="font-mono text-sm uppercase tracking-cartouche text-ink">
                AtlasKB
              </span>
            </Link>
            <nav aria-label="Primary" className="flex items-center gap-1">
              {NAV.map((item) => {
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
                        ? "border-ink text-ink"
                        : "border-transparent text-graphite hover:text-ink")
                    }
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
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

        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </main>
  );
}
