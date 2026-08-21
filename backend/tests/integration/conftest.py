import os
from collections.abc import Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


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


@pytest.fixture
def isolated_database_url() -> Iterator[str]:
    base_url = make_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
        )
    )
    database_name = f"stock_platform_isolated_{uuid4().hex}"
    assert base_url.host is not None
    assert base_url.port is not None
    assert base_url.username is not None
    with psycopg.connect(
        host=base_url.host,
        port=base_url.port,
        user=base_url.username,
        password=base_url.password,
        dbname="postgres",
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    database_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    try:
        yield database_url
    finally:
        with psycopg.connect(
            host=base_url.host,
            port=base_url.port,
            user=base_url.username,
            password=base_url.password,
            dbname="postgres",
            autocommit=True,
        ) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
