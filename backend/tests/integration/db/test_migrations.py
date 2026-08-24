import json
import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError


@pytest.fixture
def migration_database_url() -> Iterator[str]:
    base_url = make_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform",
        )
    )
    database_name = f"stock_platform_migration_{uuid4().hex}"
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


def _alembic_config(database_url: str) -> Config:
    backend_dir = Path(__file__).parents[3]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_fresh_upgrade_does_not_invent_legacy_market_context(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM market_context_snapshot")).scalar_one()
            == 0
        )
    engine.dispose()


def test_legacy_order_backfill_preserves_unknown_risk_and_context_facts(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "0012_idempotent_fill_guard")
    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO order_intent (
                    id, portfolio_id, symbol, side, quantity, decision_time,
                    execution_policy_version_id, risk_approved
                ) VALUES (
                    '70000000-0000-0000-0000-000000000018',
                    '71000000-0000-0000-0000-000000000018',
                    'NVDA', 'SELL', 7, '2026-08-20T14:30:00Z',
                    '00000000-0000-0000-0000-000000000007', true
                )
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        risk = connection.execute(
            text(
                """
                SELECT requested_weight, approved_weight, current_weight, approved_delta,
                       reference_nav, reference_price, max_order_quantity,
                       authorization_source, authorized_side
                FROM risk_decision
                WHERE id = '70000000-0000-0000-0000-000000000018'
                """
            )
        ).one()
        context = connection.execute(
            text(
                """
                SELECT qqq_trend, qqq_volatility, soxx_relative_strength, vix,
                       regime_label, source_lineage
                FROM market_context_snapshot
                WHERE id = '00000000-0000-0000-0000-000000000016'
                """
            )
        ).one()
    engine.dispose()

    assert risk == (0, 0, 0, 0, None, None, 7, "LEGACY_BACKFILL", "SELL")
    assert context == (None, None, None, None, "UNKNOWN", ["LEGACY_UNKNOWN"])


def test_0003_backfills_existing_market_data_from_unique_raw_objects(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "0002_timescale_hypertables")

    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        market_raw_id = connection.execute(
            text(
                """
                INSERT INTO raw_data_object (
                    provider, feed_type, event_time, available_at, ingested_at,
                    content_hash, raw_object_key
                ) VALUES (
                    'FIXTURE', 'MARKET_BAR', '2026-08-17T00:00:00Z',
                    '2026-08-17T00:01:00Z', '2026-08-17T00:02:00Z',
                    'market-hash', 'fixture/market'
                ) RETURNING id
                """
            )
        ).scalar_one()
        option_raw_id = connection.execute(
            text(
                """
                INSERT INTO raw_data_object (
                    provider, feed_type, event_time, available_at, ingested_at,
                    content_hash, raw_object_key
                ) VALUES (
                    'FIXTURE', 'OPTION_SNAPSHOT', '2026-08-17T00:00:00Z',
                    '2026-08-17T00:01:00Z', '2026-08-17T00:02:00Z',
                    'option-hash', 'fixture/option'
                ) RETURNING id
                """
            )
        ).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO market_bar (event_time, symbol, available_at, ingested_at, close)
                VALUES ('2026-08-17T00:00:00Z', 'TEST', '2026-08-17T00:01:00Z',
                        '2026-08-17T00:02:00Z', 100)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO option_snapshot (event_time, symbol, available_at, ingested_at)
                VALUES ('2026-08-17T00:00:00Z', 'TEST', '2026-08-17T00:01:00Z',
                        '2026-08-17T00:02:00Z')
                """
            )
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        market = connection.execute(
            text(
                "SELECT raw_data_object_id, provider, feed_type, content_hash, raw_object_key "
                "FROM market_bar"
            )
        ).one()
        option = connection.execute(
            text(
                "SELECT raw_data_object_id, provider, feed_type, content_hash, raw_object_key "
                "FROM option_snapshot"
            )
        ).one()
    engine.dispose()

    assert market == (market_raw_id, "FIXTURE", "MARKET_BAR", "market-hash", "fixture/market")
    assert option == (
        option_raw_id,
        "FIXTURE",
        "OPTION_SNAPSHOT",
        "option-hash",
        "fixture/option",
    )


def test_0007_preserves_and_hardens_existing_append_only_facts(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "0006_alert_market_bar_hardening")
    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        fill_id = connection.execute(
            text("INSERT INTO paper_fill DEFAULT VALUES RETURNING id")
        ).scalar_one()
        ledger_id = connection.execute(
            text("INSERT INTO cash_ledger DEFAULT VALUES RETURNING id")
        ).scalar_one()
    engine.dispose()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        fill = connection.execute(
            text(
                """
                SELECT order_id, symbol, execution_policy_version_id, idempotency_key
                FROM paper_fill WHERE id = :id
                """
            ),
            {"id": fill_id},
        ).one()
        ledger = connection.execute(
            text(
                """
                SELECT transaction_id, source_id, account, debit, credit, idempotency_key
                FROM cash_ledger WHERE id = :id
                """
            ),
            {"id": ledger_id},
        ).one()
        assert fill[0] == fill_id
        assert fill[1] == "FIXTURE"
        assert fill[2] is not None
        assert fill[3] == f"legacy:{fill_id}"
        assert ledger == (
            ledger_id,
            ledger_id,
            "LEGACY:CASH",
            0,
            0,
            f"legacy:{ledger_id}",
        )
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(text("UPDATE paper_fill SET created_at = created_at"))
    engine.dispose()


def test_0025_migrates_watchlist_identity_without_changing_configuration(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "0024_observability_correlation")
    engine = create_engine(migration_database_url)
    before = [
        ("CUSTOM", True, False, {"return_5m": "0.07"}),
        ("NVDA", False, True, {"price": "150.00", "volume": "1200000"}),
    ]
    with engine.begin() as connection:
        for symbol, daily_research, intraday_monitoring, thresholds in before:
            connection.execute(
                text(
                    """
                    INSERT INTO watchlist_item (
                        symbol, daily_research, intraday_monitoring, thresholds
                    ) VALUES (
                        :symbol, :daily_research, :intraday_monitoring,
                        CAST(:thresholds AS jsonb)
                    )
                    """
                ),
                {
                    "symbol": symbol,
                    "daily_research": daily_research,
                    "intraday_monitoring": intraday_monitoring,
                    "thresholds": json.dumps(thresholds),
                },
            )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        after = [
            tuple(row)
            for row in connection.execute(
                text(
                    """
                    SELECT symbol, daily_research, intraday_monitoring, thresholds
                    FROM watchlist_item
                    ORDER BY symbol
                    """
                )
            ).all()
        ]
        identities = connection.execute(
            text(
                """
                SELECT count(*), count(DISTINCT security_id), count(*) FILTER (
                    WHERE security_id IS NULL
                )
                FROM watchlist_item
                """
            )
        ).one()
        resolved = [
            tuple(row)
            for row in connection.execute(
                text(
                    """
                    SELECT watchlist.symbol, identifier.identifier_value
                    FROM watchlist_item AS watchlist
                    JOIN security_identifier_version AS identifier
                      ON identifier.security_id = watchlist.security_id
                     AND identifier.identifier_type = 'PRIMARY_SYMBOL'
                    ORDER BY watchlist.symbol
                    """
                )
            ).all()
        ]
        primary_key = (
            connection.execute(
                text(
                    """
                SELECT attribute.attname
                FROM pg_index AS index
                JOIN pg_attribute AS attribute
                  ON attribute.attrelid = index.indrelid
                 AND attribute.attnum = ANY(index.indkey)
                WHERE index.indrelid = 'watchlist_item'::regclass
                  AND index.indisprimary
                """
                )
            )
            .scalars()
            .all()
        )
    engine.dispose()

    assert after == before
    assert identities == (2, 2, 0)
    assert resolved == [("CUSTOM", "CUSTOM"), ("NVDA", "NVDA")]
    assert primary_key == ["security_id"]
