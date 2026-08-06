from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "atlaskb-api"
    log_level: str = "INFO"

    # Populated in later phases; present now so the scaffold reflects the shape.
    database_url: str = "postgresql+psycopg://atlaskb:atlaskb@postgres:5432/atlaskb"
    redis_url: str = "redis://redis:6379/0"


settings = Settings()
