import pytest
from pydantic import ValidationError
from stock_platform.settings import Settings


def test_test_environment_rejects_empty_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", database_url="")


def test_live_broker_url_is_not_a_valid_setting() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "environment": "fixture",
                "database_url": (
                    "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform"
                ),
                "live_broker_url": "https://broker.example",
            }
        )


def test_fixture_mode_requires_no_provider_credentials() -> None:
    settings = Settings(
        environment="fixture",
        database_url="postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
    )
    assert settings.fixture_mode is True
