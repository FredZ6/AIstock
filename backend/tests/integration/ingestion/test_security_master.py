from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import DBAPIError
from stock_platform.infrastructure.db.models.tables import (
    security,
    security_identifier_version,
    security_profile_version,
    watchlist_item,
)
from stock_platform.infrastructure.db.security_seed import seed_security_master

EXPECTED_SECURITIES = {
    "AVGO": ("1730168", "Nasdaq"),
    "BE": ("1664703", "NYSE"),
    "INTC": ("50863", "Nasdaq"),
    "MRVL": ("1835632", "Nasdaq"),
    "MU": ("723125", "Nasdaq"),
    "NBIS": ("1513845", "Nasdaq"),
    "NVDA": ("1045810", "Nasdaq"),
    "SKHY": ("2120882", "Nasdaq"),
    "SNDK": ("2023554", "Nasdaq"),
    "TSM": ("1046179", "NYSE"),
    "WDC": ("106040", "Nasdaq"),
}


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_security_seed_is_idempotent_and_preserves_watchlist_configuration(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        assert seed_security_master(connection) == 11
        connection.execute(
            update(watchlist_item)
            .where(watchlist_item.c.symbol == "NVDA")
            .values(
                daily_research=False,
                intraday_monitoring=False,
                thresholds={"return_5m": "0.031"},
            )
        )
        assert seed_security_master(connection) == 0

    with engine.connect() as connection:
        counts = connection.execute(
            text(
                """
                    SELECT
                      (SELECT count(*) FROM security),
                      (SELECT count(*) FROM security_identifier_version),
                      (SELECT count(*) FROM security_profile_version),
                      (SELECT count(*) FROM watchlist_item)
                    """
            )
        ).one()
        facts = connection.execute(
            select(
                security_identifier_version.c.identifier_value,
                security_profile_version.c.cik,
                security_identifier_version.c.exchange,
            )
            .join(
                security_profile_version,
                security_profile_version.c.security_id == security_identifier_version.c.security_id,
            )
            .where(security_identifier_version.c.identifier_type == "PRIMARY_SYMBOL")
            .order_by(security_identifier_version.c.identifier_value)
        ).all()
        nvda = connection.execute(
            select(
                watchlist_item.c.daily_research,
                watchlist_item.c.intraday_monitoring,
                watchlist_item.c.thresholds,
            ).where(watchlist_item.c.symbol == "NVDA")
        ).one()
    engine.dispose()

    assert counts == (11, 11, 11, 11)
    assert {symbol: (cik, exchange) for symbol, cik, exchange in facts} == EXPECTED_SECURITIES
    assert nvda == (False, False, {"return_5m": "0.031"})


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE security_identifier_version SET exchange = exchange",
        "DELETE FROM security_identifier_version",
        "UPDATE security_profile_version SET company_name = company_name",
        "DELETE FROM security_profile_version",
    ],
)
def test_security_history_is_append_only(isolated_database_url: str, statement: str) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    with engine.begin() as connection:
        seed_security_master(connection)

    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text(statement))
    engine.dispose()


def test_security_identity_is_permanent_while_history_is_versioned() -> None:
    assert security.c.id.primary_key
    assert not security_identifier_version.c.security_id.primary_key
    assert not security_profile_version.c.security_id.primary_key
