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
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentDetail = DocumentOut & {
  chunk_count: number;
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

export type ChatResponse = {
  answerable: boolean;
  answer: string;
  citations: Citation[];
  retrieved: ScoredChunk[];
};
