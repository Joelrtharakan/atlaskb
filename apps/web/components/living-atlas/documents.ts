/**
 * Placeholder document corpus for the scaffold phase.
 *
 * The index rail, transcript citations, and Living Atlas nodes all reference
 * these same ids, so a citation in the journal corresponds to exactly one node
 * on the map. Node position N maps to document N (see buildAtlas in
 * atlas-data.ts). In a later phase this list — and the layout — comes from a
 * tenant's real ingested documents.
 */

export type Territory = "spec" | "legal" | "sales";

export interface AtlasDocument {
  id: string;
  title: string;
  territory: Territory;
}

export const TERRITORY_LABELS: Record<Territory, string> = {
  spec: "Product specs",
  legal: "Legal & policy",
  sales: "Sales & GTM",
};

export const PLACEHOLDER_DOCUMENTS: AtlasDocument[] = [
  { id: "spec-arch", title: "Platform architecture", territory: "spec" },
  { id: "spec-ingest", title: "Ingestion pipeline", territory: "spec" },
  { id: "spec-retrieval", title: "Retrieval & ranking", territory: "spec" },
  { id: "spec-tenancy", title: "Multi-tenancy model", territory: "spec" },
  { id: "spec-billing", title: "Billing & metering", territory: "spec" },
  { id: "legal-dpa", title: "Data processing addendum", territory: "legal" },
  { id: "legal-privacy", title: "Privacy policy", territory: "legal" },
  { id: "legal-retention", title: "Data retention policy", territory: "legal" },
  { id: "legal-sub", title: "Subprocessor register", territory: "legal" },
  { id: "legal-tos", title: "Terms of service", territory: "legal" },
  { id: "sales-pricing", title: "Pricing & packaging", territory: "sales" },
  { id: "sales-onboard", title: "Onboarding playbook", territory: "sales" },
  { id: "sales-security", title: "Security questionnaire", territory: "sales" },
  { id: "sales-roi", title: "ROI & case studies", territory: "sales" },
  { id: "sales-comp", title: "Competitive brief", territory: "sales" },
  { id: "sales-faq", title: "Buyer FAQ", territory: "sales" },
];

/** Index of a document within the corpus, i.e. its node index in the atlas. */
export function documentIndex(id: string): number {
  return PLACEHOLDER_DOCUMENTS.findIndex((d) => d.id === id);
}
