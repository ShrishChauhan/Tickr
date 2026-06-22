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
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    # SEC requires a contact email in User-Agent; set to any valid email
    SEC_IDENTITY: str = "contact@example.com"

    model_config = {"env_file": str(_ENV_FILE)}


settings = Settings()
