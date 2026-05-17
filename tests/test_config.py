"""Tests for configuration loading."""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class _ThresholdSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    AI_CONFIDENCE_THRESHOLD: float = 0.75
    AI_AUTO_APPROVE_THRESHOLD: float = 0.95
    ENVIRONMENT: str = "development"


def test_threshold_defaults():
    from app.core.config import settings
    assert settings.AI_CONFIDENCE_THRESHOLD == 0.75
    assert settings.AI_AUTO_APPROVE_THRESHOLD == 0.95


def test_env_override(monkeypatch):
    monkeypatch.setenv("AI_CONFIDENCE_THRESHOLD", "0.80")
    s = _ThresholdSettings()
    assert s.AI_CONFIDENCE_THRESHOLD == 0.80


def test_debug_defaults_false():
    from app.core.config import settings
    assert settings.DEBUG is False


def test_test_environment_flag(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    from app.core.config import Settings
    s = Settings()
    assert s.is_test is True
