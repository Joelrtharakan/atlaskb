from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env."""

    # env_file is resolved relative to the process CWD. Run commands from the
    # repo root (where .env lives) for local development.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "atlaskb-api"
    log_level: str = "INFO"

    # No credential literals in source: supply these via the environment / .env.
    # The API refuses to start if database_url or jwt_secret is unset (see main).
    database_url: str = ""
    redis_url: str = "redis://redis:6379/0"

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
    # writes the upload) and the worker (which reads it back to parse).
    upload_dir: str = "./var/uploads"

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

    # --- LLM (generation) via OpenRouter ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Model slug is configurable, never hardcoded at the call site. Use an
    # OpenRouter slug of the form "vendor/model" (e.g. "openai/gpt-5.1").
    openrouter_model: str = "openai/gpt-5.1"

    # --- Retrieval ---
    retrieval_top_k: int = 8
    rrf_k: int = 60

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

    # --- Admin / evals ---
    # Where the eval runner writes its latest results (repo-relative, read by the
    # /admin/evals endpoint). Resolved from the process CWD (repo root in dev).
    eval_results_path: str = "eval/results/latest.json"


settings = Settings()
