// Types mirroring the AtlasKB API (apps/api/app/schemas.py).

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type UserOut = {
  id: string;
  email: string;
  created_at: string;
};

export type DocumentStatus = "processing" | "ready" | "failed";

export type DocumentOut = {
  id: string;
  filename: string;
  content_type: string;
  status: DocumentStatus;
  source?: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentDetail = DocumentOut & {
  chunk_count: number;
  can_manage_access: boolean;
};

export type Role = "viewer" | "editor" | "admin";

export type Workspace = {
  id: string;
  name: string;
  role: Role;
  created_at: string;
};

export type Member = {
  user_id: string;
  email: string;
  role: Role;
  joined_at: string;
};

export type Invite = {
  id: string;
  workspace_id: string;
  email: string;
  role: Role;
  token: string;
  invite_url: string;
  expires_at: string;
  accepted_at: string | null;
};

export type InvitePreview = {
  status: "valid" | "expired" | "accepted" | "invalid";
  email: string | null;
  role: Role | null;
  workspace_id: string | null;
  workspace_name: string | null;
};

export type AccessGrant = {
  grant_type: "role" | "user";
  role_or_user_id: string;
};

export type DocumentAccess = {
  grants: AccessGrant[];
};

export type ScoredChunk = {
  chunk_id: string;
  document_id: string;
  text: string;
  page_num: number | null;
  section: string | null;
  score: number;
  dense_score: number | null;
  sparse_score: number | null;
};

export type SearchResponse = {
  query: string;
  results: ScoredChunk[];
};

export type Citation = {
  claim: string;
  chunk_ids: string[];
};

export type TokenUsage = {
  prompt: number;
  completion: number;
  total: number;
};

export type ChatResponse = {
  answerable: boolean;
  answer: string;
  citations: Citation[];
  retrieved: ScoredChunk[];
  cached?: boolean;
  conversation_id?: string | null;
  iterations?: number;
  queries?: string[];
  usage?: TokenUsage;
};

export type Analytics = {
  tenant_id: string;
  documents_total: number;
  documents_by_status: Record<string, number>;
  chunks_total: number;
  conversations_total: number;
  messages_total: number;
  members_total: number;
  active_api_keys: number;
  cache_entries: number;
  questions_last_7_days: { day: string; count: number }[];
};

export type EvalMetrics = {
  answer_accuracy: number | null;
  citation_grounding: number | null;
  refusal_accuracy: number | null;
  retrieval_hit_rate: number | null;
  avg_tokens_per_query: number;
  latency_p50_ms: number;
  latency_p95_ms: number;
};

export type EvalResultRow = {
  question: string;
  expected_doc: string | null;
  answerable_expected: boolean;
  answerable_actual: boolean;
  retrieval_hit: boolean | null;
  answer_correct: boolean | null;
  citation_grounded: boolean | null;
  refusal_correct: boolean | null;
  tokens: number;
  latency_ms: number;
  answer: string;
};

export type EvalResults = {
  available: boolean;
  generated_at?: string;
  model?: string;
  dataset_size?: number;
  corpus_size?: number;
  metrics?: EvalMetrics;
  results?: EvalResultRow[];
};
