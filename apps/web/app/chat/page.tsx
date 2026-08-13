"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getActiveWorkspace, getLastActiveConversation } from "@/lib/tokens";

// Bare /chat has no conversation to render — it immediately replaces itself
// with either the last conversation this user was viewing in the current
// workspace (if localStorage remembers one) or a fresh, ID-less draft.
// Client-side because the choice depends on localStorage, which isn't
// available during server rendering.
export default function ChatIndexPage() {
  const router = useRouter();

  useEffect(() => {
    const workspaceId = getActiveWorkspace();
    const lastConversationId = workspaceId ? getLastActiveConversation(workspaceId) : null;
    router.replace(`/chat/${lastConversationId ?? "new"}`);
  }, [router]);

  return null;
}
