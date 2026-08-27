from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from stock_platform.application.portfolio.corporate_actions import (
    PostgresCorporateActionStore,
    ReferenceAction,
    SplitAction,
)
from stock_platform.domain.common.ids import Symbol

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


def _insert_lineage(connection: Connection) -> tuple[UUID, UUID, UUID]:
    raw_id, normalized_id, security_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        text("INSERT INTO security (id, instrument_type) VALUES (:id, 'COMMON_STOCK')"),
        {"id": security_id},
    )
    connection.execute(
        text("""
        INSERT INTO raw_data_object (id, provider, feed_type, event_time, available_at,
          ingested_at, content_hash, raw_object_key)
        VALUES (
          :id, 'FIXTURE', 'corporate_action', :now, :now, :now,
          repeat('a', 64), 'fixture/actions.json'
        )
        """),
        {"id": raw_id, "now": NOW},
    )
    connection.execute(
        text("""
        INSERT INTO normalized_record (id, raw_data_object_id, record_type, record_key,
          normalization_version, payload)
        VALUES (:id, :raw_id, 'corporate_action', 'NVDA:split', 'v2', '{}'::jsonb)
        """),
        {"id": normalized_id, "raw_id": raw_id},
    )
    return raw_id, normalized_id, security_id


def test_corporate_action_versions_are_append_only_and_point_in_time(engine: Engine) -> None:
    first_id, revision_id = uuid4(), uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        raw_id, normalized_id, security_id = _insert_lineage(connection)
        connection.execute(
            text("""
            INSERT INTO corporate_action (
              id, raw_data_object_id, normalized_record_id, security_id, provider_action_id,
              symbol, action_type, effective_at, available_at, ingested_at, provider, feed_type,
              content_hash, raw_object_key, split_ratio, currency, source_currency, details,
              supersedes_id)
            VALUES
              (:first, :raw, :normalized, :security, 'split-1', 'NVDA', 'SPLIT', :effective,
               :first_available, :now, 'FIXTURE', 'corporate_action', repeat('b',64),
               'fixture/actions.json', 2, 'USD', 'USD', '{}'::jsonb, NULL),
              (:revision, :raw, :normalized, :security, 'split-1', 'NVDA', 'SPLIT', :effective,
               :revision_available, :now, 'FIXTURE', 'corporate_action', repeat('c',64),
               'fixture/actions.json', 4, 'USD', 'USD', '{}'::jsonb, :first)
            """),
            {
                "first": first_id,
                "revision": revision_id,
                "raw": raw_id,
                "normalized": normalized_id,
                "security": security_id,
                "effective": NOW - timedelta(days=1),
                "first_available": NOW - timedelta(hours=1),
                "revision_available": NOW + timedelta(hours=1),
                "now": NOW + timedelta(hours=2),
            },
        )

        first = PostgresCorporateActionStore(connection).visible(Symbol("NVDA"), as_of=NOW)
        revised = PostgresCorporateActionStore(connection).visible(
            Symbol("NVDA"), as_of=NOW + timedelta(hours=2)
        )

        assert len(first) == 1 and isinstance(first[0], SplitAction) and first[0].ratio == 2
        assert len(revised) == 1 and isinstance(revised[0], SplitAction)
        assert revised[0].id == revision_id and revised[0].ratio == 4
        for statement in (
            "UPDATE corporate_action SET symbol='AMD' WHERE id=:id",
            "DELETE FROM corporate_action WHERE id=:id",
        ):
            savepoint = connection.begin_nested()
            with pytest.raises(DBAPIError, match="append-only"):
                connection.execute(text(statement), {"id": first_id})
            savepoint.rollback()
        transaction.rollback()


def test_symbol_change_is_typed_and_preserves_explicit_currency_metadata(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        raw_id, normalized_id, security_id = _insert_lineage(connection)
        connection.execute(
            text("""
            INSERT INTO corporate_action (
              raw_data_object_id, normalized_record_id, security_id, provider_action_id,
              symbol, action_type, effective_at, available_at, ingested_at, provider, feed_type,
              content_hash, raw_object_key, currency, source_currency, details)
            VALUES (:raw, :normalized, :security, 'rename-1', 'NVDA', 'SYMBOL_CHANGE', :now,
              :now, :now, 'FIXTURE', 'corporate_action', repeat('d',64),
              'fixture/actions.json', 'USD', 'USD', '{"new_symbol":"NVIDIA"}'::jsonb)
            """),
            {"raw": raw_id, "normalized": normalized_id, "security": security_id, "now": NOW},
        )
        action = PostgresCorporateActionStore(connection).visible(Symbol("NVDA"), as_of=NOW)[0]
        assert isinstance(action, ReferenceAction)
        assert action.action_type == "SYMBOL_CHANGE"
        assert action.details == {"new_symbol": "NVIDIA"}
        transaction.rollback()
