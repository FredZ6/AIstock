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
    config.attributes["database_url"] = database_url
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


def test_head_can_downgrade_to_0024_and_upgrade_again(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)

    command.upgrade(config, "head")
    command.downgrade(config, "0024_observability_correlation")
    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0033_ingestion_quality"
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


def test_0026_preserves_existing_market_bars_and_backfills_normalized_lineage(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "0025_ingestion_foundation")
    engine = create_engine(migration_database_url)
    raw_id = "81000000-0000-0000-0000-000000000026"
    normalized_id = "82000000-0000-0000-0000-000000000026"
    bar_id = "83000000-0000-0000-0000-000000000026"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO raw_data_object (
                    id, provider, feed_type, event_time, available_at, ingested_at,
                    content_hash, raw_object_key
                ) VALUES (
                    :raw_id, 'ALPACA', 'price_bars', '2026-08-21T14:30:00Z',
                    '2026-08-21T14:30:01Z', '2026-08-21T14:30:02Z', repeat('c', 64),
                    'live/ALPACA/price_bars/legacy.json'
                )
                """
            ),
            {"raw_id": raw_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO normalized_record (
                    id, raw_data_object_id, record_type, record_key,
                    normalization_version, payload
                ) VALUES (
                    :normalized_id, :raw_id, 'market_bar', 'NVDA:legacy',
                    'alpaca-bars-v1', '{"symbol":"NVDA"}'::jsonb
                )
                """
            ),
            {"raw_id": raw_id, "normalized_id": normalized_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO market_bar (
                    id, event_time, symbol, available_at, ingested_at, close,
                    raw_data_object_id, provider, feed_type, content_hash,
                    raw_object_key, payload
                ) VALUES (
                    :bar_id, '2026-08-21T14:30:00Z', 'NVDA',
                    '2026-08-21T14:30:01Z', '2026-08-21T14:30:02Z', 181,
                    :raw_id, 'ALPACA', 'price_bars', repeat('c', 64),
                    'live/ALPACA/price_bars/legacy.json', '{}'::jsonb
                )
                """
            ),
            {"bar_id": bar_id, "raw_id": raw_id},
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                """
                    SELECT id::text, raw_data_object_id::text,
                           normalized_record_id::text, close::text
                FROM market_bar WHERE id = :bar_id
                """
            ),
            {"bar_id": bar_id},
        ).one() == (bar_id, raw_id, normalized_id, "181")
    engine.dispose()


def test_0033_preserves_legacy_action_currency_and_uses_exact_generated_lineage(
    migration_database_url: str,
) -> None:
    config = _alembic_config(migration_database_url)
    command.upgrade(config, "0032_earnings_events")
    engine = create_engine(migration_database_url)
    raw_id = "91000000-0000-0000-0000-000000000033"
    action_id = "92000000-0000-0000-0000-000000000033"
    unrelated_id = "93000000-0000-0000-0000-000000000033"
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO raw_data_object (
              id, provider, feed_type, event_time, available_at, ingested_at,
              content_hash, raw_object_key)
            VALUES (:raw, 'FIXTURE', 'corporate_action', '2026-08-20T00:00:00Z',
              '2026-08-20T01:00:00Z', '2026-08-20T02:00:00Z', repeat('a',64),
              'fixture/legacy-action.json')
            """),
            {"raw": raw_id},
        )
        connection.execute(
            text("""
            INSERT INTO normalized_record (
              id, raw_data_object_id, record_type, record_key, normalization_version, payload)
            VALUES (:id, :raw, 'corporate_action', 'unrelated', 'corporate-action-v2', '{}'::jsonb)
            """),
            {"id": unrelated_id, "raw": raw_id},
        )
        connection.execute(
            text("""
            INSERT INTO corporate_action (
              id, raw_data_object_id, symbol, action_type, effective_at, available_at,
              ingested_at, provider, feed_type, content_hash, raw_object_key,
              cash_per_share, currency)
            VALUES (:id, :raw, 'NVDA', 'CASH_DIVIDEND', '2026-08-20T00:00:00Z',
              '2026-08-20T01:00:00Z', '2026-08-20T02:00:00Z', 'FIXTURE',
              'corporate_action', repeat('b',64), 'fixture/legacy-action.json', 1, 'EUR')
            """),
            {"id": action_id, "raw": raw_id},
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text("""
            SELECT ca.source_currency, nr.record_key
            FROM corporate_action ca
            JOIN normalized_record nr ON nr.id = ca.normalized_record_id
            WHERE ca.id = :id
            """),
            {"id": action_id},
        ).one() == ("EUR", f"legacy:{raw_id}")
    engine.dispose()
