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
  // Freshness signal (display only): 0 = fresh, 1 = fully stale.
  last_verified_at?: string | null;
  staleness?: number;
};

export type DocumentDetail = DocumentOut & {
  chunk_count: number;
  can_manage_access: boolean;
};

export type DocumentVersion = {
  id: string;
  version_number: number;
  content_hash: string | null;
  source: string | null;
  created_at: string;
  created_by: string | null;
  is_current_version: boolean;
  chunk_count: number;
};

export type DocumentVersionsResponse = {
  document_id: string;
  versions: DocumentVersion[];
};

/** One chunk as a stratum of the Core Sample. */
export type ChunkSample = {
  chunk_id: string;
  chunk_index: number;
  length: number;
  page_num: number | null;
  section: string | null;
  preview: string;
  confidence: number;
  staleness: number;
};

export type ChunkSamplesResponse = {
  document_id: string;
  filename: string;
  layers: ChunkSample[];
};

/** One document as a cell of the Dashboard relief map. */
export type ReliefCell = {
  id: string;
  filename: string;
  status: DocumentStatus;
  /** Chunk count → peak height. */
  mass: number;
  /** 0..1 → pulls the cell down into a valley. */
  staleness: number;
};

export type ReliefSummary = {
  cells: ReliefCell[];
};

export type GapCause =
  | "MISSING_DOCUMENT"
  | "OUTDATED_DOCUMENT"
  | "CONFLICTING_DOCUMENT"
  | "INSUFFICIENT_EVIDENCE"
  | "RETRIEVAL_FAILURE"
  | "PERMISSION_RESTRICTION"
  | "MODEL_FAILURE"
  | "AMBIGUOUS_QUERY"
  | "UNCLASSIFIED";

/** An unanswered-question cluster → one fog patch on the Fog-of-War map.
 * `cause`/`suggested_remediation` (Trust Layer Phase 7) are computed live
 * against current documents/ACLs each time the page loads, not from
 * historical data — see app/content_gaps.py's module docstring. */
export type ContentGap = {
  key: string;
  query: string;
  count: number;
  x: number;
  y: number;
  radius: number;
  resolved: boolean;
  members: string[];
  cause: GapCause;
  affected_user_ids: string[];
  relevant_document_ids: string[];
  suggested_remediation: string;
};

export type ContentGapsResponse = {
  gaps: ContentGap[];
};

export type QueryVolumePoint = {
  date: string;
  count: number;
};

export type QueryVolumeResponse = {
  points: QueryVolumePoint[];
};

export type LLMHealth = {
  provider: string;
  model: string;
  reachable: boolean;
  model_available: boolean;
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
  version_id: string | null;
  text: string;
  page_num: number | null;
  section: string | null;
  score: number;
  dense_score: number | null;
  sparse_score: number | null;
  rerank_score: number | null;
};

export type SearchResponse = {
  query: string;
  results: ScoredChunk[];
};

export type Citation = {
  claim: string;
  chunk_ids: string[];
};

/** SUPPORTS/COMPLEMENTS/UNRELATED/UNCERTAIN pairs are never surfaced here —
 * `/chat` only ever includes CONTRADICTS pairs in this list (Trust Layer
 * Phase 1). `relationship`/`confidence`/`chunk_id_a,b`/`claim_a,b` are new
 * in Phase 1 — older cached responses may omit them, hence optional. */
export type Conflict = {
  topic: string;
  description: string;
  chunk_ids: string[];
  document_ids: string[];
  relationship?: string;
  confidence?: number | null;
  chunk_id_a?: string | null;
  claim_a?: string | null;
  chunk_id_b?: string | null;
  claim_b?: string | null;
};

export type Evidence = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_num: number | null;
  section: string | null;
  dense_score: number | null;
  sparse_score: number | null;
  rerank_score: number | null;
  staleness: number;
  last_verified_at: string | null;
  version_number: number | null;
  is_current_version: boolean;
  /** Trust Layer Phase 4: false only under MAX_TRUST, where evidence covers
   * every retrieved chunk, not just the ones the answer actually cited. */
  is_cited?: boolean;
};

export type TokenUsage = {
  prompt: number;
  completion: number;
  total: number;
};

/** Trust Layer Phase 5: structured, evidence-derived trust signals — never a
 * single fabricated percentage. `null`/"Unknown" fields are honest gaps, not
 * missing data to paper over. */
export type TrustSummary = {
  citation_coverage: number | null;
  citation_quality: string;
  source_freshness: string;
  version: string;
  conflicts_detected: number;
  conflicts_summary: string;
  evidence_completeness: string;
  permission_check: string;
};

/** Trust Layer Phase 2: one aligned chunk-position between two versions. */
export type VersionDiffEntry = {
  kind: "ADDED" | "REMOVED" | "CHANGED" | "UNCHANGED" | "CONFLICTING";
  chunk_index: number;
  old_chunk_id: string | null;
  new_chunk_id: string | null;
  old_text: string | null;
  new_text: string | null;
};

/** Trust Layer Phase 2: present only when the question was routed off the
 * normal current-version path (historical/version-specific/comparison). */
export type TemporalInfo = {
  intent: "CURRENT" | "HISTORICAL" | "VERSION_SPECIFIC" | "COMPARE_VERSIONS" | "CHANGE_SUMMARY" | "UNKNOWN";
  document_id: string | null;
  resolved_version_number: number | null;
  compared_version_numbers: number[] | null;
  diff: VersionDiffEntry[] | null;
};

export type TrustMode = "FAST" | "BALANCED" | "MAX_TRUST";

export type ChatResponse = {
  answerable: boolean;
  answer: string;
  citations: Citation[];
  retrieved: ScoredChunk[];
  conflicts?: Conflict[];
  evidence?: Evidence[];
  message_id?: string | null;
  cached?: boolean;
  conversation_id?: string | null;
  iterations?: number;
  queries?: string[];
  usage?: TokenUsage;
  trust_mode?: TrustMode;
  trust_summary?: TrustSummary | null;
  temporal?: TemporalInfo | null;
};

export type Feedback = "up" | "down";

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  feedback: Feedback | null;
  // The full ChatResponse this assistant message was created from — null for
  // user messages and for assistant messages written before this field
  // existed (rehydration then falls back to plain text for that turn).
  response: ChatResponse | null;
};

export type ConversationSummary = {
  id: string;
  title: string;
  created_at: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: Message[];
};

export type AuditLogEntry = {
  id: string;
  user_id: string | null;
  action: string;
  target: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
};

export type AuditLogResponse = {
  entries: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
};

export type FeedbackSummaryEntry = {
  message_id: string;
  conversation_id: string;
  question: string | null;
  answer: string;
  rating: Feedback;
  user_email: string | null;
  created_at: string;
};

export type FeedbackSummaryResponse = {
  entries: FeedbackSummaryEntry[];
  up_count: number;
  down_count: number;
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
  conflict_detection_accuracy: number | null;
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
  expect_conflict: boolean | null;
  conflict_detected: boolean | null;
  conflict_correct: boolean | null;
  tokens: number;
  latency_ms: number;
  answer: string;
};

export type EvalHeadline = {
  total_questions: number | null;
  answer_accuracy: number | null;
  retrieval_hit_rate: number | null;
  citation_accuracy: number | null;
  citation_coverage: number | null;
  conflict_detection_accuracy: number | null;
  refusal_accuracy: number | null;
  permission_leakage: number | null;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  cache_hit_rate: number | null;
  adversarial_passed: number | null;
  adversarial_total: number | null;
  prompt_injection_passed: number | null;
  prompt_injection_total: number | null;
  source_files: string[];
  missing_files: string[];
};

export type EvalResults = {
  available: boolean;
  generated_at?: string;
  model?: string;
  dataset_size?: number;
  corpus_size?: number;
  metrics?: EvalMetrics;
  results?: EvalResultRow[];
  headline?: EvalHeadline;
};

export type Connector = {
  id: string;
  provider: string;
  name: string;
  status: string;
  connected: boolean;
  created_at: string;
  last_sync_at: string | null;
  last_sync_status: string | null;
};

export type OIDCConfig = {
  enabled: boolean;
};

export type OIDCExchangeResult = TokenPair & {
  email: string;
};
