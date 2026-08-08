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

    # --- Invites ---
    invite_ttl_days: int = 7
    # Public origin of the web app — invite links point at its accept page
    # (which then calls the API), not at the API endpoint directly.
    web_base_url: str = "http://localhost:3000"

    # --- Admin / evals ---
    # Where the eval runner writes its latest results (repo-relative, read by the
    # /admin/evals endpoint). Resolved from the process CWD (repo root in dev).
    eval_results_path: str = "eval/results/latest.json"


settings = Settings()
