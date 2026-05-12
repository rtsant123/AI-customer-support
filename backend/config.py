from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str  # postgresql+asyncpg://user:pass@host:5432/dbname

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    backend_url: str  # public URL (ngrok for local dev, Railway URL in prod)

    # Sarvam AI (STT only)
    sarvam_api_key: str

    # ElevenLabs (TTS)
    elevenlabs_api_key: str

    # Anthropic
    anthropic_api_key: str

    # Razorpay (optional — skip billing until ready)
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None

    # Cloudflare R2 (optional — skip recording storage until ready)
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_name: str = "call-recordings"
    r2_public_url: Optional[str] = None

    # Redis
    redis_url: str = "redis://localhost:6379"

    # App
    secret_key: str
    frontend_url: str = "http://localhost:3000"
    rate_per_min_paise: int = 1200
    jwt_expire_days: int = 30

    # Dev mode — skips wallet balance check so test calls aren't blocked
    dev_mode: bool = False

    model_config = {"env_file": ".env", "case_sensitive": False}

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def r2_enabled(self) -> bool:
        return bool(self.r2_account_id and self.r2_access_key_id and self.r2_secret_access_key)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
