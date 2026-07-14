# Loads all runtime configuration from .env via pydantic-settings
from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve .env at repo root regardless of CWD (Alembic runs from engine/)
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-6"
    LLM_BASE_URL: str = "https://api.anthropic.com"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # SEC requires a contact email in User-Agent; set to any valid email
    SEC_IDENTITY: str = "contact@example.com"
    # Finnhub — real-time US equity quotes (B4); blank disables, falls through to yfinance
    FINNHUB_API_KEY: str = ""
    # FRED — authoritative risk-free rate (Phase 9.1); blank disables, falls back to yfinance ^IRX
    FRED_API_KEY: str = ""
    # Cloudflare R2 — historical Parquet storage (Phase 7.1 follow-up)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""
    R2_ENDPOINT_URL: str = ""

    # extra="ignore": .env is shared with the web app (Supabase vars etc.) —
    # this service doesn't declare those fields and shouldn't reject them
    model_config = {"env_file": str(_ENV_FILE), "extra": "ignore"}


settings = Settings()
