import ChatAtlas from "@/components/chat/ChatAtlas";
import ChatHeader from "@/components/chat/ChatHeader";
import FieldJournal from "@/components/chat/FieldJournal";
import IndexRail from "@/components/chat/IndexRail";
import QuestionInput from "@/components/chat/QuestionInput";
import { RetrievalProvider } from "@/components/chat/retrieval";

/**
 * Chat page — "the survey table". Three co-equal zones under one neatline:
 * the quiet Index Rail (legend), the Field Journal (transcript), and the docked
 * retrieval-reactive Living Atlas. Not a sidebar-plus-cards dashboard.
 */
export default function ChatPage() {
  return (
    <RetrievalProvider>
      <main className="h-screen overflow-hidden p-3 sm:p-5">
        <div className="neatline flex h-full flex-col">
          <ChatHeader />

          <div className="grid min-h-0 flex-1 grid-cols-[210px_minmax(0,1fr)] lg:grid-cols-[210px_minmax(0,1fr)_minmax(340px,42%)]">
            {/* Index Rail — quiet legend. */}
            <div className="hidden min-h-0 border-r border-graphite/25 sm:block">
              <IndexRail />
            </div>

            {/* Field Journal + ruled input. */}
            <div className="flex min-h-0 flex-col">
              <div className="min-h-0 flex-1">
                <FieldJournal />
              </div>
              <div className="border-t border-graphite/25">
                <QuestionInput />
              </div>
            </div>

            {/* Living Atlas — docked, retrieval-reactive. */}
            <div className="relative hidden min-h-0 overflow-hidden border-l border-graphite/25 lg:block">
              <ChatAtlas />
              <span className="marginalia pointer-events-none absolute left-4 top-4 text-[0.65rem] uppercase tracking-cartouche text-pewter">
                Living Atlas
              </span>
            </div>
          </div>
        </div>
      </main>
    </RetrievalProvider>
  );
}
