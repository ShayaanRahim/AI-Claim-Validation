"""Application configuration"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """Application settings"""
    model_config = ConfigDict(env_file=".env")

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/claim_validation"

    AI_CONFIDENCE_THRESHOLD: float = 0.75
    AI_AUTO_APPROVE_THRESHOLD: float = 0.95


settings = Settings()
