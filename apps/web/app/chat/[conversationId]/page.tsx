import { ChatView } from "@/components/chat/ChatView";
import { AppShell } from "@/components/ui/AppShell";

// The survey table: the Living Atlas (3D, lazy-loaded; 2D fallback when
// degraded) beside the citations panel. See docs/design/frontend-design-plan.md §4.
//
// The URL is the source of truth for the active conversation — `[conversationId]`
// is either a real conversation id (re-hydrated from GET /conversations/{id}
// on mount, see ChatView) or the literal string "new" for an ID-less draft
// that only becomes a real, addressable conversation on its first message.
// This is what fixes the "navigate away and back loses history" bug: the
// previous single `/chat` route kept the transcript only in React state,
// which resets on unmount — nothing survived a remount. A URL persists
// across navigation and page refresh, and this page always re-hydrates from
// it rather than trusting any in-memory state to have survived.
export default function ChatPage({ params }: { params: { conversationId: string } }) {
  return (
    <AppShell>
      <ChatView conversationId={params.conversationId} />
    </AppShell>
  );
}
