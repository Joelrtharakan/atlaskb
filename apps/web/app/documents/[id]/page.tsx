import { DocumentDetailView } from "@/components/documents/DocumentDetailView";
import { AppShell } from "@/components/ui/AppShell";

export default function DocumentDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell>
      <DocumentDetailView id={params.id} />
    </AppShell>
  );
}
