from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from stock_platform.application.portfolio.corporate_actions import (
    CorporateActionProcessor,
    PostgresCorporateActionStore,
    ReferenceAction,
    SplitAction,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.position import Position
from stock_platform.infrastructure.db.models.tables import corporate_action

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
          :content_hash, :object_key
        )
        """),
        {
            "id": raw_id,
            "now": NOW,
            "content_hash": raw_id.hex * 2,
            "object_key": f"fixture/actions/{raw_id}.json",
        },
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


def test_latest_version_is_scoped_by_provider_and_selected_by_availability(engine: Engine) -> None:
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
              (:old, :raw, :normalized, :security, 'shared-id', 'NVDA', 'SPLIT', :old_effective,
               :old_available, :ingested, 'ALPACA', 'corporate_action', repeat('1',64),
               'fixture/old.json', 2, 'USD', 'USD', '{}'::jsonb, NULL),
              (:revision, :raw, :normalized, :security, 'shared-id', 'NVDA', 'SPLIT',
               :new_effective,
               :new_available, :ingested, 'ALPACA', 'corporate_action', repeat('2',64),
               'fixture/revision.json', 4, 'USD', 'USD', '{}'::jsonb, :old),
              (:latest, :raw, :normalized, :security, 'shared-id', 'NVDA', 'SPLIT',
               :latest_effective, :latest_available, :ingested, 'ALPACA', 'corporate_action',
               repeat('4',64), 'fixture/latest.json', 8, 'USD', 'USD', '{}'::jsonb, :revision),
              (:other, :raw, :normalized, :security, 'shared-id', 'NVDA', 'SPLIT', :old_effective,
               :other_available, :ingested, 'FIXTURE', 'corporate_action', repeat('3',64),
               'fixture/other.json', 3, 'USD', 'USD', '{}'::jsonb, NULL)
            """),
            {
                "old": uuid4(),
                "revision": uuid4(),
                "latest": uuid4(),
                "other": uuid4(),
                "raw": raw_id,
                "normalized": normalized_id,
                "security": security_id,
                "old_effective": NOW - timedelta(days=1),
                "new_effective": NOW - timedelta(days=2),
                "latest_effective": NOW - timedelta(days=3),
                "old_available": NOW - timedelta(hours=2),
                "new_available": NOW - timedelta(hours=1),
                "latest_available": NOW - timedelta(minutes=30),
                "other_available": NOW - timedelta(minutes=30),
                "ingested": NOW,
            },
        )

        store = PostgresCorporateActionStore(connection)
        first = store.visible(Symbol("NVDA"), as_of=NOW - timedelta(minutes=90))
        visible = store.visible(Symbol("NVDA"), as_of=NOW)

        assert sorted(action.ratio for action in visible if isinstance(action, SplitAction)) == [
            3,
            8,
        ]
        adjusted = CorporateActionProcessor().adjust_position(
            Position(Symbol("NVDA"), Decimal("10")), first
        )
        latest_alpaca = tuple(
            action
            for action in visible
            if isinstance(action, SplitAction) and action.ratio == Decimal("8")
        )
        revision = CorporateActionProcessor().adjust_position_with_gaps(adjusted, latest_alpaca)
        assert revision.position.quantity == Decimal("20")
        assert revision.gaps[0].reason == "REVISED_CORPORATE_ACTION_REQUIRES_REPLAY"
        transaction.rollback()


@pytest.mark.parametrize(
    ("action_type", "split_ratio", "cash_per_share", "stock_ratio"),
    [
        ("SPLIT", 2, 1, None),
        ("STOCK_DIVIDEND", None, None, 0),
        ("SYMBOL_CHANGE", 2, None, None),
    ],
)
def test_corporate_action_values_are_exclusive_and_positive(
    engine: Engine,
    action_type: str,
    split_ratio: int | None,
    cash_per_share: int | None,
    stock_ratio: int | None,
) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        raw_id, normalized_id, security_id = _insert_lineage(connection)
        with pytest.raises(DBAPIError):
            connection.execute(
                text("""
                INSERT INTO corporate_action (
                  raw_data_object_id, normalized_record_id, security_id, provider_action_id,
                  symbol, action_type, effective_at, available_at, ingested_at, provider,
                  feed_type, content_hash, raw_object_key, split_ratio, cash_per_share,
                  stock_ratio, currency, source_currency, details)
                VALUES (:raw, :normalized, :security, :provider_action_id, 'NVDA', :action_type,
                  :now, :now, :now, 'FIXTURE', 'corporate_action', repeat('e',64),
                  'fixture/invalid.json', :split_ratio, :cash_per_share, :stock_ratio,
                  'USD', 'USD', '{}'::jsonb)
                """),
                {
                    "raw": raw_id,
                    "normalized": normalized_id,
                    "security": security_id,
                    "provider_action_id": str(uuid4()),
                    "action_type": action_type,
                    "now": NOW,
                    "split_ratio": split_ratio,
                    "cash_per_share": cash_per_share,
                    "stock_ratio": stock_ratio,
                },
            )
        transaction.rollback()


def test_new_corporate_action_requires_explicit_source_currency(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        raw_id, normalized_id, security_id = _insert_lineage(connection)
        with pytest.raises(DBAPIError):
            connection.execute(
                text("""
                INSERT INTO corporate_action (
                  raw_data_object_id, normalized_record_id, security_id, provider_action_id,
                  symbol, action_type, effective_at, available_at, ingested_at, provider,
                  feed_type, content_hash, raw_object_key, cash_per_share, currency, details)
                VALUES (:raw, :normalized, :security, 'missing-source', 'NVDA',
                  'CASH_DIVIDEND', :now, :now, :now, 'FIXTURE', 'corporate_action',
                  repeat('f',64), 'fixture/missing-source.json', 1, 'EUR', '{}'::jsonb)
                """),
                {"raw": raw_id, "normalized": normalized_id, "security": security_id, "now": NOW},
            )
        transaction.rollback()


def test_revision_must_supersede_latest_provider_action_version(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        raw_id, normalized_id, security_id = _insert_lineage(connection)
        common = {
            "raw": raw_id,
            "normalized": normalized_id,
            "security": security_id,
            "now": NOW,
        }
        connection.execute(
            text("""
            INSERT INTO corporate_action (
              raw_data_object_id, normalized_record_id, security_id, provider_action_id,
              symbol, action_type, effective_at, available_at, ingested_at, provider,
              feed_type, content_hash, raw_object_key, split_ratio, currency,
              source_currency, details)
            VALUES (:raw, :normalized, :security, 'chain-required', 'NVDA', 'SPLIT',
              :now, :first_available, :now, 'ALPACA', 'corporate_action', repeat('6',64),
              'fixture/chain-first.json', 2, 'USD', 'USD', '{}'::jsonb)
            """),
            common | {"first_available": NOW - timedelta(hours=1)},
        )
        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match="must supersede latest"):
            connection.execute(
                text("""
                INSERT INTO corporate_action (
                  raw_data_object_id, normalized_record_id, security_id, provider_action_id,
                  symbol, action_type, effective_at, available_at, ingested_at, provider,
                  feed_type, content_hash, raw_object_key, split_ratio, currency,
                  source_currency, details)
                VALUES (:raw, :normalized, :security, 'chain-required', 'NVDA', 'SPLIT',
                  :now, :now, :now, 'ALPACA', 'corporate_action', repeat('7',64),
                  'fixture/chain-missing.json', 4, 'USD', 'USD', '{}'::jsonb)
                """),
                common,
            )
        savepoint.rollback()
        transaction.rollback()


def test_concurrent_first_versions_cannot_fork_revision_chain(engine: Engine) -> None:
    with engine.begin() as connection:
        raw_id, normalized_id, security_id = _insert_lineage(connection)
    provider_action_id = f"concurrent-{uuid4()}"
    barrier = Barrier(2)

    def insert_root(offset: int) -> bool:
        try:
            with engine.begin() as connection:
                barrier.wait(timeout=5)
                connection.execute(
                    text("""
                    INSERT INTO corporate_action (
                      raw_data_object_id, normalized_record_id, security_id, provider_action_id,
                      symbol, action_type, effective_at, available_at, ingested_at, provider,
                      feed_type, content_hash, raw_object_key, split_ratio, currency,
                      source_currency, details)
                    VALUES (:raw, :normalized, :security, :provider_action_id, 'AAPL', 'SPLIT',
                      :now, :available, :now, 'ALPACA', 'corporate_action', :hash,
                      :object_key, 2, 'USD', 'USD', '{}'::jsonb)
                    """),
                    {
                        "raw": raw_id,
                        "normalized": normalized_id,
                        "security": security_id,
                        "provider_action_id": provider_action_id,
                        "now": NOW,
                        "available": NOW - timedelta(seconds=offset),
                        "hash": str(offset) * 64,
                        "object_key": f"fixture/concurrent-{offset}.json",
                    },
                )
            return True
        except DBAPIError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(insert_root, (1, 2)))

    assert sum(outcomes) == 1
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(corporate_action)
                .where(
                    corporate_action.c.provider == "ALPACA",
                    corporate_action.c.provider_action_id == provider_action_id,
                )
            ).scalar_one()
            == 1
        )
