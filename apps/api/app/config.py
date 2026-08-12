from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The repo-root .env, resolved from this file's location so the app finds it no
# matter which directory it's launched from (repo root or apps/api). A .env in
# the current working directory still takes precedence for per-run overrides.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        extra="ignore",
    )

    app_name: str = "atlaskb-api"
    log_level: str = "INFO"

    # No credential literals in source: supply these via the environment / .env.
    # The API refuses to start if database_url or jwt_secret is unset (see main).
    database_url: str = ""
    redis_url: str = "redis://redis:6379/0"

    # --- Connection pooling (Trust Layer T11.2) ---
    # SQLAlchemy's QueuePool defaults (size 5, overflow 10) were sized for a
    # single local-dev instance, not N horizontally-scaled API replicas
    # sharing one Postgres. Made explicit and configurable rather than left
    # implicit: pool_size + max_overflow is the ceiling of connections THIS
    # process can open, and (replicas * that ceiling) must stay under
    # Postgres's own max_connections (100 by default) — see T11.2's note in
    # docker-compose.yml about PgBouncer for when replica_count grows enough
    # that per-process pooling alone isn't sufficient.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # How long a request waits for a free connection before erroring, rather
    # than hanging indefinitely if the pool is genuinely exhausted.
    db_pool_timeout: int = 30
    # redis-py's ConnectionPool has no cap by default -- unbounded growth
    # under load is exactly the kind of silent, un-observed limit T11.2
    # exists to close. Sized generously above db_pool_size + db_max_overflow
    # since Redis is used for cache, rate limiting, and the T11.1 concurrency
    # counter all from the same process.
    redis_max_connections: int = 50

    # Browser origins allowed to call the API (the Next.js web app).
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # --- Auth ---
    # Required in every environment; supply via JWT_SECRET (see .env.example).
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14

    # --- Storage ---
    # Where uploaded source documents are written. Shared between the API (which
    # writes the upload) and the worker (which reads it back to parse) — so it is
    # resolved to an absolute path anchored at the repo root. If both ran from
    # different working directories a relative path would silently point them at
    # different folders and ingestion would fail with FileNotFoundError.
    upload_dir: str = "var/uploads"

    @field_validator("upload_dir")
    @classmethod
    def _absolutize_upload_dir(cls, value: str) -> str:
        p = Path(value)
        return str(p if p.is_absolute() else (_REPO_ROOT / p))

    # --- Embeddings ---
    # Backend for producing chunk/query vectors. NOT served via OpenRouter.
    #   "local" -> sentence-transformers, runs in-process, no API key.
    #   "openai" -> OpenAI embeddings API (requires OPENAI_API_KEY).
    #   "fake"  -> deterministic hash-based vectors, for fast tests only.
    embedding_backend: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    # Force CPU by default: PyTorch's Metal/MPS backend aborts inside a forked
    # Celery worker on macOS. CPU is plenty for MiniLM-sized models.
    embedding_device: str = "cpu"
    openai_api_key: str = ""

    # --- LLM (generation) ---
    # Provider abstraction. Both providers speak the OpenAI-compatible chat API,
    # so a single client (openai.OpenAI + base_url) serves both — no extra dep.
    #   "ollama"     -> local Ollama daemon, no API key, no quotas (default).
    #   "openrouter" -> OpenRouter hosted models (paid / free-tier daily cap).
    llm_provider: str = "ollama"

    # Ollama (local). Bound to loopback; never exposed publicly. Its OpenAI-
    # compatible endpoint lives under {base_url}/v1.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"

    # OpenRouter (optional fallback). Kept so LLM_PROVIDER=openrouter still works.
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Model slug is configurable, never hardcoded at the call site. Use an
    # OpenRouter slug of the form "vendor/model" (e.g. "openai/gpt-5.1").
    openrouter_model: str = "openai/gpt-5.1"

    @property
    def llm_model(self) -> str:
        """Active generation model for the configured provider. Used at the call
        sites and folded into the cache key so switching provider/model never
        serves a stale answer produced by a different model."""
        return self.ollama_model if self.llm_provider == "ollama" else self.openrouter_model

    # --- Retrieval ---
    retrieval_top_k: int = 3
    rrf_k: int = 60
    # Component-toggle flags (Trust Layer T9.0) — for the eval/ablation harness
    # ONLY, set via environment/.env before the process starts. Never exposed as
    # a per-request override, so a real user can never change these.
    #   retrieval_mode: "hybrid" (default, dense+sparse+RRF) | "dense_only"
    #     (skips the sparse/BM25 query and RRF fusion entirely) | "sparse_only"
    #     (skips the dense pgvector query and query embedding entirely).
    retrieval_mode: str = "hybrid"
    # Retrieval scoped to each document's current version only (Phase T1). False
    # reproduces pre-T1 behavior: every version's chunks are searchable at once.
    version_aware_retrieval: bool = True
    # Cross-document conflict detection (Phase T4). False reproduces pre-T4
    # behavior: no conflict-check LLM call is ever made.
    conflict_detection_enabled: bool = True
    # Per-stage timing breakdown on ChatResponse.timing (Trust Layer T9.5),
    # for the eval harness only — off by default so a normal client never gets
    # internal stage timings in its response payload.
    expose_timing: bool = False

    # --- Conflict detection (Trust Layer Phase 1: structured pipeline) ---
    # Empty string -> falls back to llm_model. Lets relationship classification
    # run on a smaller/faster model than generation (execution rule: "do not
    # force conflict detection to use the generation model").
    conflict_detection_model: str = ""
    # Candidate pairs are ranked by lexical/topic similarity and only the top N
    # are ever sent to the LLM, so classification cost stays bounded regardless
    # of how many chunks were retrieved (never O(n^2) LLM calls).
    conflict_max_candidate_pairs: int = 8
    # Minimum entity-overlap (Jaccard) similarity for a cross-document claim
    # pair to be considered a conflict candidate at all — below this, claims
    # are assumed to be about different subjects and never reach the LLM.
    # 0.05, not a rounder-looking 0.1+: measured against
    # eval/conflicts/dataset.json, every genuinely-unrelated pair in that
    # benchmark scores exactly 0.0 similarity, while several real
    # (differently-worded) conflicts score as low as 0.06-0.10 — so 0.05 is
    # the highest threshold that doesn't cost real recall on this benchmark,
    # not an arbitrary round number. See eval/conflicts/README.md.
    conflict_candidate_min_similarity: float = 0.05
    # Confidence assigned to deterministic (non-LLM) classifications — see
    # app/conflict_detection/deterministic.py for exactly what triggers each
    # and eval/conflicts/README.md for how these were chosen (fixed constants,
    # not learned/calibrated against a validation curve — documented as such).
    conflict_deterministic_numeric_confidence: float = 0.9
    conflict_deterministic_date_confidence: float = 0.85
    conflict_deterministic_agreement_confidence: float = 0.85

    @property
    def conflict_model(self) -> str:
        """Active conflict-classification model — a dedicated, possibly
        smaller/faster model if configured, else the generation model."""
        return self.conflict_detection_model or self.llm_model

    # --- Content-gap cause classification (Trust Layer Phase 7) ---
    # Cross-encoder rerank scores are unbounded but roughly centered on 0 for
    # the default ms-marco model (negative = judged irrelevant) — a judgment
    # call for "too weak to count as real coverage", not a calibrated
    # probability. See app/content_gaps.py's classification docstring.
    content_gap_weak_evidence_rerank_threshold: float = 0.0
    # Above this staleness (0..1, same scale as Document.staleness), a gap's
    # closest-matching source is classified OUTDATED_DOCUMENT rather than
    # treated as valid current coverage.
    content_gap_staleness_threshold: float = 0.8

    # --- Trust modes (Trust Layer Phase 4) ---
    # MAX_TRUST widens the conflict-detection candidate net relative to the
    # BALANCED defaults above — passed as per-call overrides (never a global
    # mutation of the settings above, which are shared across concurrent
    # requests) by app.routers.chat when body.trust_mode == "MAX_TRUST".
    max_trust_candidate_min_similarity: float = 0.0
    max_trust_max_candidate_pairs: int = 20

    # --- Reranking ---
    # Second-stage relevance scoring over RRF's fused candidate pool, before
    # truncating to top_k. RRF blends dense/sparse *rank position* only — it has
    # no notion of how much better one candidate is than another. A cross-encoder
    # reads the query and a chunk's text together and scores relevance directly,
    # correcting RRF's ordering before the final top_k is chosen.
    #   "cross-encoder" -> sentence-transformers CrossEncoder, in-process, no API key.
    #   "fake"          -> deterministic term-overlap scoring, for fast tests only.
    rerank_enabled: bool = True
    rerank_backend: str = "cross-encoder"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_device: str = "cpu"
    # How many RRF-fused candidates get reranked before truncating to top_k.
    # Wider than top_k so the cross-encoder can promote a match RRF ranked lower.
    rerank_candidate_k: int = 20

    # --- Freshness / staleness (display only) ---
    # A document is considered fully stale once it is this many days past its
    # last verification (or creation, if never verified). Drives the relief-map
    # valleys and fog signal in the UI; has no effect on retrieval or ACL.
    staleness_max_age_days: int = 90

    # --- Agent (LangGraph) ---
    # Max retrieval iterations before the agent must answer with what it has.
    # Bounded to keep runaway re-querying (and cost) in check.
    agent_max_iterations: int = 3

    # --- Semantic cache (Redis) ---
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_prefix: str = "atlaskb:cache"

    # --- Rate limiting (Redis) ---
    rate_limit_enabled: bool = True
    rate_limit_user_per_min: int = 60
    rate_limit_tenant_per_min: int = 600
    rate_limit_prefix: str = "atlaskb:ratelimit"

    # --- API keys ---
    # Plaintext prefix for generated keys and how many chars form the lookup id.
    api_key_prefix: str = "atlk"
    api_key_lookup_len: int = 16

    # --- Invites ---
    invite_ttl_days: int = 7
    # Public origin of the web app — invite links point at its accept page
    # (which then calls the API), not at the API endpoint directly.
    web_base_url: str = "http://localhost:3000"

    # --- Admin / evals ---
    # Where the eval runner writes its latest results, read by the
    # /admin/evals endpoint. Anchored at the repo root, same as upload_dir
    # above and for the same reason: the API is normally launched with
    # `uv run --project apps/api`, whose CWD is apps/api, not the repo root —
    # a bare relative path here silently pointed at apps/api/eval/results/,
    # which never existed, so /admin/evals always read as unavailable even
    # with real results sitting one directory up (found while building T9.8).
    eval_results_path: str = "eval/results/latest.json"

    @field_validator("eval_results_path")
    @classmethod
    def _absolutize_eval_results_path(cls, value: str) -> str:
        p = Path(value)
        return str(p if p.is_absolute() else (_REPO_ROOT / p))

    # --- Connectors: Google Drive (Trust Layer Phase 11) ---
    # OAuth client registered by the workspace owner in Google Cloud Console
    # (APIs & Services > Credentials > OAuth client ID > Web application).
    # Empty by default: the connectors router refuses to start an OAuth flow
    # until these are set, rather than failing deep inside the Google client.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Must exactly match a redirect URI registered on the OAuth client.
    google_redirect_uri: str = "http://localhost:8000/connectors/google/callback"
    # Symmetric key (Fernet, url-safe base64, 32 bytes) encrypting each
    # ConnectorConfig's refresh token before it's stored in credentials_ref.
    # Generate with: python -c "from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())". Required only once a Drive
    # connector is actually created; not needed for the rest of the app.
    connector_token_key: str = ""

    # --- Auth: SSO / OIDC (Trust Layer Phase 11) ---
    # Generic OIDC — works with any standards-compliant provider (Google
    # Workspace, Okta, Azure AD, ...) via its discovery document, not
    # provider-specific code. Empty issuer/client_id means SSO is off:
    # /auth/oidc/config reports disabled and the login/callback endpoints
    # refuse to start a flow, same pattern as the Drive connector's
    # GOOGLE_CLIENT_ID gate.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/auth/oidc/callback"

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

    # --- LLM generation concurrency (Trust Layer T11.1) ---
    # Real ceiling is provider/hardware-specific, not something the app can
    # infer — 1 matches local Ollama on typical (non-GPU-dedicated) dev
    # hardware, where a single generation already saturates it. Raise this
    # explicitly for a hosted provider or beefier local inference hardware.
    llm_concurrency_enabled: bool = True
    llm_concurrency_limit: int = 1
    # How long a request waits for a free generation slot before it gets a
    # clean 429 instead of eventually timing out against the LLM itself.
    llm_concurrency_queue_timeout_seconds: float = 20.0
    llm_concurrency_prefix: str = "atlaskb:llmconcurrency"


settings = Settings()
