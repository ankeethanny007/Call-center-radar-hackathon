from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets live only in the ignored .env file."""

    database_url: str = "sqlite:///./callradar.db"
    media_root: Path = Path("./data")
    cors_origins: str = "http://localhost:3000"
    # Optional for local development; required for a deployment that exposes the API.
    # The Next.js server uses this value server-side only, never through NEXT_PUBLIC_*.
    api_access_token: str | None = None
    media_url_ttl_seconds: int = 900
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 45.0
    analysis_provider: str = "openai"  # "openai" or "rules" for offline/dev
    validate_evidence_with_llm: bool = True
    whisper_model: str = "small"
    whisper_compute_type: str = "int8"
    whisper_download_root: Path = Path("./work/models")
    whisper_utterance_gap_seconds: float = 1.0
    whisper_max_utterance_seconds: float = 12.0
    storage_provider: str = "local"  # local or supabase
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    supabase_bucket: str = "call-audio"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
