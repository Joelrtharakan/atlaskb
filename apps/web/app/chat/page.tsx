import { ChatView } from "@/components/chat/ChatView";
import { AppShell } from "@/components/ui/AppShell";

// Plain, well-typeset survey table. The 3D Living Atlas is intentionally not
// wired in this phase — see docs/design/frontend-design-plan.md §4.
export default function ChatPage() {
  return (
    <AppShell>
      <ChatView />
    </AppShell>
  );
}
