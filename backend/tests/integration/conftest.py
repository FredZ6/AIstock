import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
    )
    instance = create_engine(database_url)
    try:
        yield instance
    finally:
        instance.dispose()
