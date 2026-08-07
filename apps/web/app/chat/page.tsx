import { ChatView } from "@/components/chat/ChatView";
import { AppShell } from "@/components/ui/AppShell";

// The survey table: the Living Atlas (3D, lazy-loaded; 2D fallback when
// degraded) beside the citations panel. See docs/design/frontend-design-plan.md §4.
export default function ChatPage() {
  return (
    <AppShell>
      <ChatView />
    </AppShell>
  );
}
