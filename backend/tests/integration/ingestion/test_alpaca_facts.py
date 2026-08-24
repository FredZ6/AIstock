import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, insert, inspect, select, text, update
from sqlalchemy.exc import DBAPIError
from stock_platform.application.ingestion.normalizers.alpaca import (
    AlpacaBar,
    AlpacaNewsArticle,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.ingestion.models import MarketDataCoverage, MarketSession
from stock_platform.infrastructure.db.models.tables import (
    market_bar,
    news_article,
    normalized_record,
    raw_data_object,
)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_0026_adds_alpaca_fact_schema_and_database_guards(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    engine = create_engine(isolated_database_url)
    inspector = inspect(engine)

    table_names = inspector.get_table_names()
    assert "news_article" in table_names
    assert "market_trade" not in table_names
    market_bar_columns = {column["name"] for column in inspector.get_columns("market_bar")}
    assert {"normalized_record_id", "coverage", "session"} <= market_bar_columns
    with engine.connect() as connection:
        guarded_tables = set(
            connection.execute(
                text(
                    """
                    SELECT event_object_table
                    FROM information_schema.triggers
                    WHERE trigger_name = 'enforce_append_only'
                      AND event_object_table IN ('market_bar', 'news_article')
                    """
                )
            ).scalars()
        )
        lineage_guard = connection.execute(
            text(
                """
                SELECT count(*)
                FROM pg_trigger
                WHERE tgname = 'require_normalized_market_bar_lineage'
                  AND NOT tgisinternal
                """
            )
        ).scalar_one()

    assert guarded_tables == {"market_bar", "news_article"}
    assert lineage_guard == 1
    engine.dispose()


def test_alpaca_fact_store_is_idempotent_and_preserves_append_only_lineage(
    isolated_database_url: str,
) -> None:
    command.upgrade(_alembic_config(isolated_database_url), "head")
    module_name = "stock_platform.infrastructure.ingestion.fact_store"
    try:
        module_spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        module_spec = None
    assert module_spec is not None, "Alpaca fact store is missing"
    store_type = importlib.import_module(module_name).PostgresAlpacaFactStore
    engine = create_engine(isolated_database_url)
    published_at = datetime(2026, 8, 21, 13, tzinfo=UTC)
    available_at = datetime(2026, 8, 21, 14, 31, tzinfo=UTC)

    with engine.begin() as connection:
        bar_raw_id = connection.execute(
            insert(raw_data_object)
            .values(
                provider="ALPACA",
                feed_type="price_bars",
                event_time=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
                available_at=available_at,
                ingested_at=available_at,
                content_hash="a" * 64,
                raw_object_key=f"live/ALPACA/price_bars/{'a' * 64}.json",
            )
            .returning(raw_data_object.c.id)
        ).scalar_one()
        bar_normalized_id = connection.execute(
            insert(normalized_record)
            .values(
                raw_data_object_id=bar_raw_id,
                record_type="market_bar",
                record_key="NVDA:2026-08-21T14:30:00Z:IEX",
                normalization_version="alpaca-bars-v1",
                payload={"symbol": "NVDA", "close": "181.00"},
            )
            .returning(normalized_record.c.id)
        ).scalar_one()
        news_raw_id = connection.execute(
            insert(raw_data_object)
            .values(
                provider="ALPACA",
                feed_type="company_news",
                event_time=published_at,
                available_at=available_at,
                ingested_at=available_at,
                content_hash="b" * 64,
                raw_object_key=f"live/ALPACA/company_news/{'b' * 64}.json",
            )
            .returning(raw_data_object.c.id)
        ).scalar_one()
        news_normalized_id = connection.execute(
            insert(normalized_record)
            .values(
                raw_data_object_id=news_raw_id,
                record_type="news_article",
                record_key="987654",
                normalization_version="alpaca-news-v1",
                payload={"article_id": "987654", "symbols": ["NVDA"]},
            )
            .returning(normalized_record.c.id)
        ).scalar_one()
        store = store_type(connection)
        bar = AlpacaBar(
            symbol=Symbol("NVDA"),
            event_time=datetime(2026, 8, 21, 14, 30, tzinfo=UTC),
            available_at=available_at,
            open=Decimal("180.10"),
            high=Decimal("181.25"),
            low=Decimal("179.80"),
            close=Decimal("181.00"),
            volume=Decimal("125000"),
            coverage=MarketDataCoverage.IEX,
            session=MarketSession.REGULAR,
            payload={"t": "2026-08-21T14:30:00Z", "c": "181.00"},
        )
        article = AlpacaNewsArticle(
            article_id="987654",
            symbols=(Symbol("NVDA"),),
            headline="Fixture research update",
            published_at=published_at,
            available_at=available_at,
            observed_at=None,
            pit_eligible=False,
            source="fixture-wire",
            summary="Redacted fixture.",
            payload={"id": "987654", "symbols": ["NVDA"]},
        )

        first_bar_id = store.persist_bar(
            raw_id=bar_raw_id,
            normalized_id=bar_normalized_id,
            bar=bar,
        )
        assert (
            store.persist_bar(
                raw_id=bar_raw_id,
                normalized_id=bar_normalized_id,
                bar=bar,
            )
            == first_bar_id
        )
        first_news_id = store.persist_news(
            raw_id=news_raw_id,
            normalized_id=news_normalized_id,
            article=article,
        )
        assert (
            store.persist_news(
                raw_id=news_raw_id,
                normalized_id=news_normalized_id,
                article=article,
            )
            == first_news_id
        )

        assert connection.execute(select(func.count()).select_from(market_bar)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(news_article)).scalar_one() == 1
        assert connection.execute(
            select(market_bar.c.raw_data_object_id, market_bar.c.normalized_record_id)
        ).one() == (bar_raw_id, bar_normalized_id)
        assert connection.execute(
            select(news_article.c.raw_data_object_id, news_article.c.normalized_record_id)
        ).one() == (news_raw_id, news_normalized_id)

    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(update(market_bar).values(close=Decimal("999")))
    with engine.connect() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(text("DELETE FROM news_article"))
    engine.dispose()
