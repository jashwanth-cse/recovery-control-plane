from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Revenue Recovery Control Plane"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://recovery:recovery@localhost:5432/recovery_control_plane"
    )
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:13000"]
    razorpay_key_id: str | None = None
    razorpay_key_secret: SecretStr | None = None
    razorpay_api_base_url: str = "https://api.razorpay.com/v1"
    razorpay_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    razorpay_test_mode_only: bool = True
    razorpay_webhook_secret: SecretStr | None = None
    razorpay_webhook_previous_secret: SecretStr | None = None
    razorpay_webhook_max_body_bytes: int = Field(
        default=1_000_000, gt=0, le=5_000_000
    )
    recovery_window_days: int = Field(default=14, gt=0, le=180)
    abandoned_order_age_minutes: int = Field(default=30, gt=0, le=10_080)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
