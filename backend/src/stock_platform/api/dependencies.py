from collections.abc import Iterator
from functools import lru_cache
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header
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


def authenticate_human_actor(settings: Settings, authorization: str | None) -> HumanActor:
    token = settings.admin_api_token
    actor_id = settings.admin_actor_id
    if token is None or actor_id is None or authorization is None:
        raise ApiError(403, "FORBIDDEN", "Authenticated human identity required")
    scheme, separator, presented = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not compare_digest(presented, token.get_secret_value())
    ):
        raise ApiError(403, "FORBIDDEN", "Authenticated human identity required")
    return HumanActor(actor_id.strip(), authenticated=True, is_human=True)


def get_human_actor(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> HumanActor:
    return authenticate_human_actor(settings, authorization)
