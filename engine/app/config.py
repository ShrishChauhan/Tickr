# Loads all runtime configuration from .env via pydantic-settings
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-6"
    LLM_BASE_URL: str = "https://api.anthropic.com"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env"}


settings = Settings()
