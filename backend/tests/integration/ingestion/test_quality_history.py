from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from stock_platform.application.market_data.quality import (
    QualityAssessment,
    QualityDimension,
    QualityStatus,
)
from stock_platform.infrastructure.db.models.tables import data_quality_observation
from stock_platform.infrastructure.ingestion.fact_store import PostgresQualityFactStore

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
