"""Application configuration loaded from environment variables."""

from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — values are read from `.env` and the process environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="",
        description="PostgreSQL URL (use postgresql+asyncpg:// for the async engine)",
    )
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_anon_key: str = Field(default="", description="Supabase anonymous key")
    supabase_service_role_key: str = Field(
        default="",
        description="Supabase service role key (server-side only)",
    )
    jwt_secret_key: str = Field(default="", description="Secret for signing JWTs")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        description="Access token lifetime in minutes",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        description="Refresh token lifetime in days",
    )
    groq_api_key: str = Field(default="", description="Groq API key for LLM and vision")
    gemini_api_key: str = Field(
        default="",
        description="Optional Google Gemini API key (legacy; optional)",
    )
    upstash_redis_rest_url: str = Field(
        default="",
        description="Upstash Redis REST URL",
    )
    upstash_redis_rest_token: str = Field(
        default="",
        description="Upstash Redis REST token",
    )
    otp_expire_minutes: int = Field(default=5, ge=1, description="OTP validity window")
    app_env: str = Field(default="development", description="Environment name")
    app_name: str = Field(default="Ingredex", description="Application display name")

    smtp_host: str = Field(default="", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP port (587 for STARTTLS)")
    smtp_username: str = Field(default="", description="SMTP auth username")
    smtp_password: str = Field(default="", description="SMTP auth password")
    smtp_from_email: str = Field(default="", description="Sender email address")
    smtp_from_name: str = Field(default="Ingredex", description="Sender display name")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Self:
        """Ensure critical secrets are present when running in production."""
        if self.app_env.lower() == "production":
            missing: list[str] = []
            if not self.database_url.strip():
                missing.append("DATABASE_URL")
            if not self.jwt_secret_key.strip():
                missing.append("JWT_SECRET_KEY")
            if not self.supabase_url.strip():
                missing.append("SUPABASE_URL")
            if not self.upstash_redis_rest_url.strip() or not self.upstash_redis_rest_token.strip():
                missing.append("UPSTASH_CREDENTIALS")
            if missing:
                msg = f"Missing required settings for production: {', '.join(missing)}"
                raise ValueError(msg)
        return self


settings = Settings()
