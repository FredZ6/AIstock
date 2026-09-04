"""Test-only HTTP entry point: no local .env credentials or external provider calls."""

import os

from pydantic_settings import SettingsConfigDict
from stock_platform.api.dependencies import get_settings
from stock_platform.api.main import app
from stock_platform.settings import Settings

if os.environ.get("RUN_API_BROWSER") != "1":
    raise RuntimeError("Only available to the isolated browser test harness")
database_url = os.environ["DATABASE_URL"]
if "/stock_platform_isolated_" not in database_url:
    raise RuntimeError("Browser tests require an isolated test database")


class BrowserSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, extra="forbid")


app.dependency_overrides[get_settings] = lambda: BrowserSettings(
    environment="test",
    database_url=database_url,
    redis_url="redis://127.0.0.1:1/0",
)
