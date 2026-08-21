from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from stock_platform.api.schemas.errors import ApiError
from stock_platform.application.learning.promotion import HumanActor
from stock_platform.settings import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def _engine(database_url: str) -> Engine:
    return create_engine(database_url)


def get_connection(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Connection]:
    with _engine(settings.database_url).begin() as connection:
        yield connection


def get_human_actor() -> HumanActor:
    raise ApiError(403, "FORBIDDEN", "Authenticated human identity required")
