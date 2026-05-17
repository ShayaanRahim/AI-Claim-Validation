"""Application configuration loaded from environment variables."""
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/claim_validation"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    AI_CONFIDENCE_THRESHOLD: float = 0.75
    AI_AUTO_APPROVE_THRESHOLD: float = 0.95

    AUTH_DISABLED: bool = False
    SYSTEM_API_KEY: str = Field(default="dev-system-key-change-me")
    REVIEWER_API_KEY: str = Field(default="dev-reviewer-key-change-me")

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT == "test"

    @property
    def sqlalchemy_echo(self) -> bool:
        return self.DEBUG and self.ENVIRONMENT == "development"


settings = Settings()
