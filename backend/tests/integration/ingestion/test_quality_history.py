from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from stock_platform.application.market_data.quality import (
    QualityAssessment,
    QualityDimension,
    QualityStatus,
)
from stock_platform.domain.ingestion.models import FeedType
from stock_platform.infrastructure.db.models.tables import (
    data_quality_observation,
    ingestion_cursor,
)
from stock_platform.infrastructure.ingestion.fact_store import PostgresQualityFactStore
from stock_platform.infrastructure.ingestion.job_store import IngestionJobStore

NOW = datetime(2026, 8, 27, 14, tzinfo=UTC)


def _migrate(database_url: str) -> None:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_quality_schema_stores_raw_dimensions_without_ui_grade(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    columns = {column["name"] for column in inspect(engine).get_columns("data_quality_observation")}

    assert {
        "raw_data_object_id",
        "normalized_record_id",
        "provider",
        "dataset",
        "dimension",
        "status",
        "observed_at",
        "freshness",
        "coverage",
        "delay",
        "conflict",
        "policy_version",
        "details",
    } <= columns
    assert "grade" not in columns
    assert "provider_health_snapshot" not in inspect(engine).get_table_names()
    assert "reconciliation_result" not in inspect(engine).get_table_names()
    engine.dispose()


def test_quality_history_is_idempotent_append_only_and_has_complete_lineage(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    raw_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO raw_data_object (
                    id, provider, feed_type, event_time, available_at, ingested_at,
                    content_hash, raw_object_key
                ) VALUES (
                    :raw_id, 'ALPACA', 'price_bars', :event_time, :available_at, :ingested_at,
                    :content_hash, :object_key
                )
                """
            ),
            {
                "raw_id": raw_id,
                "event_time": NOW - timedelta(minutes=2),
                "available_at": NOW - timedelta(minutes=1),
                "ingested_at": NOW,
                "content_hash": "a" * 64,
                "object_key": "quality/" + "a" * 64 + ".json",
            },
        )
        normalized_id = connection.execute(
            text(
                """
                INSERT INTO normalized_record (
                    raw_data_object_id, record_type, record_key, normalization_version, payload
                ) VALUES (:raw_id, 'market_bar', 'NVDA:quality', 'quality-source-v1', '{}')
                RETURNING id
                """
            ),
            {"raw_id": raw_id},
        ).scalar_one()
        store = PostgresQualityFactStore(connection)
        assessment = QualityAssessment(
            dimension=QualityDimension.FRESHNESS,
            status=QualityStatus.DEGRADED,
            provider="ALPACA",
            dataset="price_bars",
            observed_at=NOW,
            freshness=timedelta(minutes=2),
            coverage="SIP",
            delay=timedelta(minutes=1),
            conflict=False,
            policy_version="data-quality-v1",
            details={"reason": "late"},
        )
        first = store.persist(
            raw_id=raw_id,
            normalized_id=normalized_id,
            assessment=assessment,
        )
        second = store.persist(
            raw_id=raw_id,
            normalized_id=normalized_id,
            assessment=assessment,
        )
        assert first == second
        invalid = QualityAssessment(
            dimension=QualityDimension.CONFLICT,
            status=QualityStatus.FAIL,
            provider="SEC",
            dataset="price_bars",
            observed_at=NOW,
            freshness=None,
            coverage=None,
            delay=None,
            conflict=True,
            policy_version="data-quality-v1",
            details={"fault": "identity mismatch"},
        )
        with pytest.raises(ValueError, match="identity"):
            store.persist(raw_id=raw_id, normalized_id=normalized_id, assessment=invalid)
        assert connection.execute(select(data_quality_observation.c.id)).scalars().all() == [first]

    with engine.connect() as connection:
        row = connection.execute(select(data_quality_observation)).mappings().one()
        assert row["raw_data_object_id"] == raw_id
        assert row["normalized_record_id"] == normalized_id
        assert row["freshness"] == timedelta(minutes=2)
        assert row["delay"] == timedelta(minutes=1)
        assert row["conflict"] is False

        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text("UPDATE data_quality_observation SET status = 'PASS' WHERE id = :id"),
                {"id": first},
            )
        connection.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text("DELETE FROM data_quality_observation WHERE id = :id"),
                {"id": first},
            )
    engine.dispose()


def test_quality_failure_does_not_advance_cursor_and_retry_is_idempotent(
    isolated_database_url: str,
) -> None:
    _migrate(isolated_database_url)
    engine = create_engine(isolated_database_url)
    raw_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO raw_data_object (
              id, provider, feed_type, event_time, available_at, ingested_at,
              content_hash, raw_object_key)
            VALUES (:id, 'ALPACA', 'price_bars', :now, :now, :now,
              repeat('9',64), 'quality/cursor-boundary.json')
            """),
            {"id": raw_id, "now": NOW},
        )
        normalized_id = connection.execute(
            text("""
            INSERT INTO normalized_record (
              raw_data_object_id, record_type, record_key, normalization_version, payload)
            VALUES (:raw, 'market_bar', 'NVDA:cursor-boundary', 'quality-v1', '{}')
            RETURNING id
            """),
            {"raw": raw_id},
        ).scalar_one()
        failed = QualityAssessment(
            dimension=QualityDimension.CONFLICT,
            status=QualityStatus.FAIL,
            provider="SEC",
            dataset="price_bars",
            observed_at=NOW,
            freshness=None,
            coverage=None,
            delay=None,
            conflict=True,
            policy_version="data-quality-v1",
            details={"fault": "between fact and quality"},
        )
        with pytest.raises(ValueError, match="identity"):
            PostgresQualityFactStore(connection).persist(
                raw_id=raw_id, normalized_id=normalized_id, assessment=failed
            )

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(data_quality_observation)
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(select(func.count()).select_from(ingestion_cursor)).scalar_one() == 0
        )

    valid = QualityAssessment(
        dimension=QualityDimension.CONFLICT,
        status=QualityStatus.PASS,
        provider="ALPACA",
        dataset="price_bars",
        observed_at=NOW,
        freshness=None,
        coverage="IEX",
        delay=None,
        conflict=False,
        policy_version="data-quality-v1",
        details={},
    )
    with engine.begin() as connection:
        first = PostgresQualityFactStore(connection).persist(
            raw_id=raw_id, normalized_id=normalized_id, assessment=valid
        )
    jobs = IngestionJobStore(engine)
    assert jobs.advance_cursor(
        provider="ALPACA",
        dataset=FeedType.PRICE_BARS,
        scope_key="NVDA",
        expected_generation=0,
        cursor={"page_token": "complete"},
        watermark=NOW,
        now=NOW,
    )
    with engine.begin() as connection:
        replay = PostgresQualityFactStore(connection).persist(
            raw_id=raw_id, normalized_id=normalized_id, assessment=valid
        )
    assert replay == first
    assert not jobs.advance_cursor(
        provider="ALPACA",
        dataset=FeedType.PRICE_BARS,
        scope_key="NVDA",
        expected_generation=0,
        cursor={"page_token": "stale"},
        watermark=NOW,
        now=NOW,
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(data_quality_observation)
            ).scalar_one()
            == 1
        )
        assert connection.execute(select(ingestion_cursor.c.generation)).scalar_one() == 1
    engine.dispose()
