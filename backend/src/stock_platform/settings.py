from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with a deliberately closed, paper-only surface."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    environment: Literal["fixture", "paper", "test"] = "fixture"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
        min_length=1,
    )
    minio_endpoint: str = "localhost:59000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "fixture-raw"
    minio_secure: bool = False
    redis_url: str = "redis://localhost:56379/0"
    otel_export_enabled: bool = False
    prometheus_multiproc_dir: str | None = None
    admin_api_token: SecretStr | None = None
    admin_actor_id: str | None = None
    max_active_agent_runs: int = Field(default=2, ge=1)
    sec_user_agent: str | None = None
    alpaca_data_key: str | None = None
    alpaca_data_secret: str | None = None
    fmp_api_key: str | None = None

    @property
    def fixture_mode(self) -> bool:
        return self.environment in {"fixture", "test"}

    @model_validator(mode="after")
    def complete_admin_identity(self) -> "Settings":
        if (self.admin_api_token is None) != (self.admin_actor_id is None):
            raise ValueError("admin_api_token and admin_actor_id must be configured together")
        if self.admin_actor_id is not None and not self.admin_actor_id.strip():
            raise ValueError("admin_actor_id cannot be blank")
        return self
