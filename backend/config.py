from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str  # postgresql+asyncpg://user:pass@host:5432/dbname

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    backend_url: str

    # Sarvam AI (STT only)
    sarvam_api_key: str

    # ElevenLabs (TTS)
    elevenlabs_api_key: str

    # Anthropic
    anthropic_api_key: str

    # Razorpay
    razorpay_key_id: str
    razorpay_key_secret: str

    # Cloudflare R2
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str = "call-recordings"
    r2_public_url: str

    # Redis
    redis_url: str = "redis://localhost:6379"

    # App
    secret_key: str  # used for JWT signing
    frontend_url: str = "http://localhost:3000"
    rate_per_min_paise: int = 1200
    jwt_expire_days: int = 30

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
