from typing import Literal

from pydantic import Field
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
        default="postgresql+psycopg://postgres:postgres@localhost:5432/stock_platform",
        min_length=1,
    )

    @property
    def fixture_mode(self) -> bool:
        return self.environment in {"fixture", "test"}
