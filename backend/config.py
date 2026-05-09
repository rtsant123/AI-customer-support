from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str

    # Exotel
    exotel_api_key: str
    exotel_api_token: str
    exotel_sid: str
    exotel_caller_id: str

    # Sarvam AI
    sarvam_api_key: str

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
    secret_key: str
    frontend_url: str = "http://localhost:3000"
    rate_per_min_paise: int = 1200

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
