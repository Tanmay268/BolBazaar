"""Environment-driven settings. Secrets come only from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    app_base_url: str = "http://127.0.0.1:8000"
    cors_origins: str = "http://localhost:5173,http://localhost,https://localhost,capacitor://localhost"
    database_url: str = "sqlite:///./data/bolbazaar.db"
    seed_demo_data: bool = True
    # Seed the demo organisation outside development too (hackathon hosting). JWT_SECRET is still required.
    demo_mode: bool = False

    jwt_secret: str = ""
    jwt_ttl_minutes: int = 720

    # Self-service accounts. Managers can only sign up with this code; empty disables manager sign-up.
    allow_signup: bool = True
    manager_signup_code: str = ""
    default_org_name: str = "BolBazaar Distributors"

    # offline | live. speech_mode / reasoner_mode override provider_mode independently.
    provider_mode: str = "offline"
    speech_mode: str = ""
    reasoner_mode: str = ""

    gnani_api_key: str = ""
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_stt_model: str = "prisma-v3.0"
    gnani_timeout_ms: int = 25000
    gnani_max_retries: int = 2
    gnani_max_segment_seconds: float = 28.0
    gnani_max_concurrent_requests: int = 1
    gnani_daily_call_budget: int = 200
    # Optional overrides of the per-language TTS profile.
    gnani_tts_model: str = ""
    gnani_tts_voice: str = ""
    gnani_tts_speed: float = 1.0

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = ""
    azure_openai_timeout_ms: int = 30000
    azure_openai_max_retries: int = 2

    audio_storage_dir: str = "./data/audio"
    audio_retention_hours: int = 24
    max_audio_bytes: int = 15 * 1024 * 1024
    max_audio_seconds: float = 120.0

    @field_validator("database_url")
    @classmethod
    def _driver(cls, url: str) -> str:
        """Hosted Postgres hands out postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg driver named."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def jwt_key(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        if self.app_env == "development":
            return DEV_JWT_SECRET
        raise RuntimeError("JWT_SECRET must be set outside development")

    @property
    def speech(self) -> str:
        return (self.speech_mode or self.provider_mode).lower()

    @property
    def reasoner(self) -> str:
        return (self.reasoner_mode or self.provider_mode).lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
