/**
 * Single source of truth for the /how-it-works copy and numbers, shared by
 * both the static (reduced-motion/low-power) reading experience and the
 * pinned-3D scroll journey — so the two can never drift out of sync with
 * each other, or with the real system (README, measured eval/load results).
 * Every number here traces back to README.md — do not add one that doesn't.
 */

export interface Landmark {
  id: string;
  name: string;
  subtitle: string;
  detail: string;
}

export const LANDMARKS: Landmark[] = [
  {
    id: "camp",
    name: "The survey camp",
    subtitle: "Next.js frontend",
    detail: "Where every visit starts — the app you're using right now.",
  },
  {
    id: "gate",
    name: "The checkpoint",
    subtitle: "FastAPI gateway",
    detail: "Auth, RBAC/ACL, rate limiting, and the cache lookup all happen here, before anything else runs.",
  },
  {
    id: "tower",
    name: "The compass tower",
    subtitle: "LangGraph agent loop",
    detail: "Plans the retrieval query, judges whether it has enough, and decides whether to look again.",
  },
  {
    id: "vault",
    name: "The vault",
    subtitle: "Postgres + pgvector",
    detail: "Chunks, documents, workspaces, and access grants — the record of everything that's been surveyed.",
  },
  {
    id: "signal-fire",
    name: "The signal fire",
    subtitle: "Redis",
    detail: "The query cache and the rate limits — the fast, disposable layer in front of the vault.",
  },
  {
    id: "survey-team",
    name: "The survey team",
    subtitle: "Celery ingestion worker",
    detail: "Parses, chunks, embeds, and writes every document that comes in — the ones who chart new ground.",
  },
  {
    id: "peaks",
    name: "The distant peaks",
    subtitle: "LLM + embedding backends",
    detail: "Ollama (qwen3:8b, local, default) or OpenRouter for generation; sentence-transformers (local, default) or OpenAI for embeddings.",
  },
];

export interface Step {
  id: string;
  n: number;
  title: string;
  body: string;
}

export const STEPS: Step[] = [
  {
    id: "signup",
    n: 1,
    title: "Sign up, get a workspace",
    body: "Every request is scoped to a workspace, via a header or a workspace-bound API key. Roles — viewer, editor, admin — gate write routes. A single choke-point query, document_visible_clause, enforces per-document access grants across every retrieval path, so there's no code path that can accidentally leak a restricted document.",
  },
  {
    id: "upload",
    n: 2,
    title: "Upload a document",
    body: "Ingestion runs asynchronously on a Celery worker: parse → chunk → embed, in batches of 64 → write. Re-ingesting the same document is idempotent — old chunks are deleted before the new ones are inserted. The document's status flips to ready, or failed with the error captured.",
  },
  {
    id: "ask",
    n: 3,
    title: "Ask a question",
    body: "The question is handed to the agent — a bounded loop that decides what to retrieve, checks whether it has enough, and only then writes an answer. (More on that at the next waypoint.)",
  },
  {
    id: "map",
    n: 4,
    title: "The answer becomes a map",
    body: "The Living Atlas takes the cited chunks, flies the camera to the documents that answered you, and draws a lit thread between them. Reduced-motion or low-power sessions get an equivalent 2D fallback with no WebGL dependency — same information, no camera move.",
  },
];

export interface AgentNode {
  id: string;
  label: string;
  heading: number;
  body: string;
}

export const AGENT_NODES: AgentNode[] = [
  {
    id: "plan",
    label: "plan",
    heading: 0,
    body: "Condenses the question into a standalone retrieval query — on a follow-up turn, this is what resolves “it” or “that policy” against the conversation history.",
  },
  {
    id: "retrieve",
    label: "retrieve",
    heading: Math.PI / 2,
    body: "Hybrid search, scoped to the caller's workspace and ACL visibility: dense pgvector similarity and sparse Postgres full-text, merged with Reciprocal Rank Fusion (1/(k+rank), k=60).",
  },
  {
    id: "assess",
    label: "assess",
    heading: Math.PI,
    body: "An LLM call judges whether the retrieved chunks are enough. If not, and the loop is still under its bound, it proposes a refined query and loops back to plan.",
  },
  {
    id: "generate",
    label: "generate",
    heading: (3 * Math.PI) / 2,
    body: "Produces the grounded answer and a citation mapping from every claim to the chunk ID(s) that support it — or the explicit refusal, if nothing relevant was retrieved.",
  },
];

export const AGENT_MAX_ITERATIONS = 3;

export const CACHE_NOTE =
  "Before any of that runs, a Redis cache is checked — keyed on workspace · user · model · normalized question. A repeat of the same question comes back with no model call at all.";

export interface Stat {
  id: string;
  label: string;
  value: number;
  suffix?: string;
  decimals?: number;
  note?: string;
}

export const QUALITY_STATS: Stat[] = [
  { id: "accuracy", label: "Answer accuracy", value: 100, suffix: "%", note: "8/8" },
  { id: "grounding", label: "Citation grounding", value: 100, suffix: "%" },
  { id: "refusal", label: "Refusal accuracy", value: 100, suffix: "%" },
  { id: "hit-rate", label: "Retrieval hit rate", value: 100, suffix: "%" },
  { id: "tokens", label: "Avg tokens / query", value: 2118, note: "~2,118" },
];
export const QUALITY_NOTE =
  "8-question labelled set, 4-document corpus — a smoke-grade quality gate, not a benchmark.";

export interface LatencyRow {
  id: string;
  path: string;
  p50: string;
  p95: string;
  throughput: string;
  cacheHit: string;
}

export const LATENCY_ROWS: LatencyRow[] = [
  { id: "search-cold", path: "/search cold", p50: "75 ms", p95: "101 ms", throughput: "127 req/s", cacheHit: "—" },
  { id: "search-warm", path: "/search warm", p50: "29 ms", p95: "49 ms", throughput: "627 req/s", cacheHit: "100%" },
  { id: "chat-cold", path: "/chat cold", p50: "23.2 s", p95: "31.2 s", throughput: "—", cacheHit: "—" },
  { id: "chat-warm", path: "/chat warm", p50: "20 ms", p95: "45 ms", throughput: "418 req/s", cacheHit: "100%" },
];
export const LATENCY_NOTE =
  "/chat cold latency is dominated by the model call, not AtlasKB. The cache turns a repeated question from ~23s to ~20ms — roughly 1000× — at $0 model cost.";

export const COST_NOTES = [
  "$0 with the default local Ollama provider — no API calls leave the machine.",
  "$0 for any cache hit, regardless of provider.",
  "~$0.003–$0.006 / query projected on paid small hosted models at the measured token rate — a projection, not billed.",
];

export interface ToolkitItem {
  id: string;
  label: string;
  group: "Backend" | "Frontend" | "Tooling";
}

export const TOOLKIT: ToolkitItem[] = [
  { id: "python", label: "Python 3.12", group: "Backend" },
  { id: "fastapi", label: "FastAPI", group: "Backend" },
  { id: "pydantic", label: "Pydantic v2", group: "Backend" },
  { id: "sqlalchemy", label: "SQLAlchemy 2", group: "Backend" },
  { id: "alembic", label: "Alembic", group: "Backend" },
  { id: "postgres", label: "Postgres + pgvector", group: "Backend" },
  { id: "redis", label: "Redis", group: "Backend" },
  { id: "celery", label: "Celery", group: "Backend" },
  { id: "langgraph", label: "LangGraph", group: "Backend" },
  { id: "st", label: "sentence-transformers", group: "Backend" },
  { id: "auth", label: "argon2 + PyJWT", group: "Backend" },
  { id: "structlog", label: "structlog", group: "Backend" },
  { id: "nextjs", label: "Next.js 14", group: "Frontend" },
  { id: "ts", label: "TypeScript", group: "Frontend" },
  { id: "tailwind", label: "Tailwind", group: "Frontend" },
  { id: "r3f", label: "React Three Fiber", group: "Frontend" },
  { id: "drei", label: "drei + three", group: "Frontend" },
  { id: "playwright", label: "Playwright", group: "Frontend" },
  { id: "uv", label: "uv workspace", group: "Tooling" },
  { id: "docker", label: "Docker Compose", group: "Tooling" },
  { id: "ruff", label: "ruff", group: "Tooling" },
  { id: "pytest", label: "pytest", group: "Tooling" },
];
