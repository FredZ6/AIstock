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
    alpaca_entitlement_coverage: str | None = None
    alpaca_entitlement_version: str | None = None
    alpaca_overnight: bool = False
    alpaca_sip_delay_seconds: int | None = Field(default=None, ge=0)
    fmp_api_key: str | None = None
    alpha_vantage_api_key: SecretStr | None = None

    @property
    def fixture_mode(self) -> bool:
        return self.environment in {"fixture", "test"}

    @model_validator(mode="after")
    def complete_admin_identity(self) -> "Settings":
        if (self.admin_api_token is None) != (self.admin_actor_id is None):
            raise ValueError("admin_api_token and admin_actor_id must be configured together")
        if self.admin_actor_id is not None and not self.admin_actor_id.strip():
            raise ValueError("admin_actor_id cannot be blank")
        if (self.alpaca_data_key is None) != (self.alpaca_data_secret is None):
            raise ValueError("alpaca_data_key and alpaca_data_secret must be configured together")
        if (self.alpaca_entitlement_coverage is None) != (self.alpaca_entitlement_version is None):
            raise ValueError(
                "Alpaca entitlement coverage and entitlement version are required together"
            )
        if self.alpaca_entitlement_coverage is not None:
            coverage = {
                value.strip().upper()
                for value in self.alpaca_entitlement_coverage.split(",")
                if value.strip()
            }
            if not coverage or not coverage <= {"IEX", "SIP"}:
                raise ValueError("Alpaca entitlement coverage must contain only IEX or SIP")
            if not self.alpaca_entitlement_version or not self.alpaca_entitlement_version.strip():
                raise ValueError("Alpaca entitlement version cannot be blank")
            if "SIP" in coverage and self.alpaca_sip_delay_seconds is None:
                raise ValueError("Alpaca SIP entitlement requires an explicit delay")
            if "SIP" not in coverage and self.alpaca_sip_delay_seconds is not None:
                raise ValueError("Alpaca SIP delay requires SIP entitlement")
        return self
