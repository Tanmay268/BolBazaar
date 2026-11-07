"""Environment-driven settings. Secrets come only from the environment."""

from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# No fixed development secret exists any more: a published default would let anyone forge admin tokens against
# a dev server that is reachable on the LAN (HOST=0.0.0.0) with live provider keys. Without JWT_SECRET, development
# uses a random per-process secret (tokens simply stop working after a restart).
_EPHEMERAL_JWT_SECRET = secrets.token_urlsafe(48)
MIN_JWT_SECRET_CHARS = 32
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


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
    # Password given to the seeded demo accounts. The default is public; set DEMO_PASSWORD for any shared deployment.
    demo_password: str = "demo123"
    # Private password for the real `admin` account. The demo accounts (rep, manager, view-only recruiter) stay public.
    admin_password: str = ""
    # Serve /docs, /redoc and /openapi.json. Empty means: only when APP_ENV=development.
    expose_docs: str = ""

    jwt_secret: str = ""
    jwt_ttl_minutes: int = 720

    # Self-service accounts. Managers can only sign up with this code; empty disables manager sign-up.
    allow_signup: bool = True
    manager_signup_code: str = ""
    # Optional invite code for field-rep sign-up (empty = open). Strongest control against account farming.
    rep_signup_code: str = ""
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

    # ---- Cost protection (see security/CREDIT_PROTECTION_REPORT.md). A limit of 0 means "blocked", never "unlimited".
    # Emergency switches. Env flags need a restart; the admin API (PUT /v1/admin/providers/{name}) flips them live.
    ai_services_enabled: bool = True
    gnani_enabled: bool = True
    azure_enabled: bool = True

    # Per-user limits (fixed windows, UTC). stt = Gnani speech-to-text calls (one per <=28 s segment).
    user_stt_per_minute: int = 8
    user_stt_per_hour: int = 60
    user_stt_per_day: int = 120
    user_stt_audio_seconds_per_day: int = 3600
    user_tts_per_minute: int = 6
    user_tts_per_hour: int = 40
    user_tts_per_day: int = 80
    user_tts_chars_per_day: int = 15000
    user_llm_per_minute: int = 12
    user_llm_per_hour: int = 100
    user_llm_per_day: int = 250
    user_llm_est_tokens_per_day: int = 400000
    user_max_concurrent_ai: int = 2
    max_process_attempts_per_capture: int = 4
    # Catalogue: products a user may add per day, and the cap on active products (all of them go to the LLM each visit).
    user_products_per_day: int = 60
    user_bulk_products_per_day: int = 300
    max_products: int = 500
    user_bug_reports_per_day: int = 10
    global_bug_reports_per_day: int = 500
    max_catalogue_text_chars: int = 6000
    max_catalogue_draft_items: int = 100

    # Global (all users) ceilings per provider. The Gnani request ceiling reuses gnani_daily_call_budget.
    global_gnani_per_minute: int = 30
    global_gnani_audio_seconds_per_day: int = 7200
    global_gnani_tts_chars_per_day: int = 60000
    global_azure_per_minute: int = 60
    global_azure_requests_per_day: int = 800
    global_azure_est_tokens_per_day: int = 1500000
    budget_warn_fraction: float = 0.8
    azure_daily_call_budget: int = 2400            # in-client backstop; counts HTTP attempts including retries
    azure_max_output_tokens: int = 2048
    azure_max_concurrent_requests: int = 4
    queue_wait_seconds: float = 3.0                # wait this long for a provider slot, then fail fast

    # Circuit breaker (per provider, per process).
    breaker_failure_threshold: int = 5
    breaker_cooldown_seconds: int = 60
    breaker_fatal_cooldown_seconds: int = 900      # credits exhausted / key rejected: stop calling for 15 min

    # Input limits.
    max_transcript_chars: int = 4000
    max_correction_chars: int = 500
    max_tts_chars: int = 600
    max_json_body_bytes: int = 262144
    multipart_overhead_bytes: int = 1048576
    ffmpeg_max_concurrent: int = 2

    # Request rate limits (in-memory sliding windows, per process; see the report for the multi-instance caveat).
    rl_ip_per_minute: int = 240
    rl_user_per_minute: int = 120
    rl_login_ip_per_minute: int = 20
    rl_login_failures_per_account: int = 8         # failures per 15 minutes before the account is cooled down
    rl_login_failures_per_ip: int = 30
    rl_register_ip_per_hour: int = 5
    signup_global_per_day: int = 300
    # Number of reverse proxies in front of the app. 0 = trust only the socket peer (X-Forwarded-For is ignored).
    trusted_proxy_count: int = 0

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
            if len(self.jwt_secret) < MIN_JWT_SECRET_CHARS and self.app_env != "development":
                raise RuntimeError(f"JWT_SECRET must be at least {MIN_JWT_SECRET_CHARS} characters outside development")
            return self.jwt_secret
        if self.app_env == "development":
            return _EPHEMERAL_JWT_SECRET
        raise RuntimeError("JWT_SECRET must be set outside development")

    @property
    def docs_enabled(self) -> bool:
        if self.expose_docs:
            return self.expose_docs.strip().lower() in {"1", "true", "yes", "on"}
        return self.app_env == "development"

    def warnings(self) -> list[str]:
        """Configuration that is legal but dangerous. Logged at start-up and asserted by the security tests."""
        out: list[str] = []
        live = "live" in {self.speech, self.reasoner}
        seeded = self.seed_demo_data and (self.app_env == "development" or self.demo_mode)
        if seeded and self.demo_password == "demo123":
            out.append("Demo accounts use the public default password (set DEMO_PASSWORD).")
        if seeded and self.app_env != "development" and not self.admin_password:
            out.append("ADMIN_PASSWORD is not set: the real admin account shares the public demo password.")
        if live and seeded and self.host not in LOOPBACK_HOSTS:
            out.append("Live providers are enabled while demo accounts exist and the server listens on a non-loopback host.")
        if live and self.allow_signup and not self.rep_signup_code:
            out.append("Open rep sign-up with live providers: anyone can create accounts that spend provider credits (set REP_SIGNUP_CODE).")
        if self.app_env != "development" and self.trusted_proxy_count == 0:
            out.append("TRUSTED_PROXY_COUNT is 0: behind a reverse proxy every client shares the proxy's IP for IP rate limits.")
        if not self.ai_services_enabled:
            out.append("AI_SERVICES_ENABLED=false: all paid provider calls are disabled.")
        return out

    @property
    def speech(self) -> str:
        return (self.speech_mode or self.provider_mode).lower()

    @property
    def reasoner(self) -> str:
        return (self.reasoner_mode or self.provider_mode).lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
