from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from stock_platform.application.portfolio.accounting import initial_funding
from stock_platform.application.portfolio.corporate_actions import (
    CashDividend,
    CorporateActionProcessor,
    PostgresCorporateActionStore,
    SplitAction,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.ledger import cash_balance, is_balanced
from stock_platform.domain.portfolio.position import Position

DECISION_TIME = datetime(2026, 8, 21, 14, 30, tzinfo=UTC)


def test_corporate_actions_are_point_in_time_and_idempotent(engine: Engine) -> None:
    portfolio_id = uuid4()
    raw_id = uuid4()
    split_id = uuid4()
    dividend_id = uuid4()
    raw_hash = uuid4().hex * 2
    raw_key = f"fixture/corporate-actions/{raw_id}.json"
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            text(
                """
                INSERT INTO raw_data_object (
                    id, provider, feed_type, event_time, available_at, ingested_at,
                    content_hash, raw_object_key
                ) VALUES (
                    :id, 'FIXTURE', 'corporate_action', :event_time, :available_at, :ingested_at,
                    :content_hash, :raw_object_key
                )
                """
            ),
            {
                "id": raw_id,
                "event_time": DECISION_TIME - timedelta(days=1),
                "available_at": DECISION_TIME - timedelta(hours=1),
                "ingested_at": DECISION_TIME,
                "content_hash": raw_hash,
                "raw_object_key": raw_key,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO corporate_action (
                    id, raw_data_object_id, symbol, action_type, effective_at, available_at,
                    ingested_at, provider, feed_type, content_hash, raw_object_key, split_ratio,
                    cash_per_share, currency
                ) VALUES
                (
                    :split_id, :raw_id, 'NVDA', 'SPLIT', :effective_at, :split_available,
                    :ingested_at, 'FIXTURE', 'corporate_action', :split_hash, :split_key,
                    2, NULL, 'USD'
                ),
                (
                    :dividend_id, :raw_id, 'NVDA', 'CASH_DIVIDEND', :effective_at,
                    :dividend_available, :ingested_at, 'FIXTURE', 'corporate_action',
                    :dividend_hash, :dividend_key, NULL, 0.5, 'USD'
                )
                """
            ),
            {
                "split_id": split_id,
                "dividend_id": dividend_id,
                "raw_id": raw_id,
                "effective_at": DECISION_TIME - timedelta(minutes=30),
                "split_available": DECISION_TIME - timedelta(minutes=10),
                "dividend_available": DECISION_TIME + timedelta(minutes=10),
                "ingested_at": DECISION_TIME + timedelta(minutes=20),
                "split_hash": raw_hash,
                "dividend_hash": raw_hash,
                "split_key": raw_key,
                "dividend_key": raw_key,
            },
        )
        store = PostgresCorporateActionStore(connection)

        first_cutoff = store.visible(Symbol("NVDA"), as_of=DECISION_TIME)
        later_cutoff = store.visible(Symbol("NVDA"), as_of=DECISION_TIME + timedelta(minutes=20))

        assert len(first_cutoff) == 1 and isinstance(first_cutoff[0], SplitAction)
        assert {type(action) for action in later_cutoff} == {SplitAction, CashDividend}
        assert all(action.available_at <= DECISION_TIME for action in first_cutoff)

        processor = CorporateActionProcessor()
        split_position = processor.adjust_position(
            Position(Symbol("NVDA"), Decimal("10")), first_cutoff
        )
        repeated_split_position = processor.adjust_position(split_position, first_cutoff)
        entries = initial_funding(portfolio_id, Decimal("1000"), "USD", DECISION_TIME)
        posted = processor.apply_dividends(entries, portfolio_id, split_position, later_cutoff)
        repeated = processor.apply_dividends(posted, portfolio_id, split_position, later_cutoff)

        assert split_position.quantity == Decimal("20")
        assert repeated_split_position.quantity == Decimal("20")
        assert cash_balance(posted, portfolio_id, "USD") == Decimal("1010")
        assert repeated == posted
        assert is_balanced(posted)
        transaction.rollback()


def test_corporate_action_query_rejects_naive_cutoff(engine: Engine) -> None:
    with engine.connect() as connection, pytest.raises(ValueError, match="timezone-aware"):
        PostgresCorporateActionStore(connection).visible(
            Symbol("NVDA"), as_of=datetime(2026, 8, 21, 14, 30)
        )
