from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from stock_platform.application.portfolio.corporate_actions import (
    AdrRatioChange,
    CashDividend,
    CorporateActionProcessor,
    ReferenceAction,
    StockDividend,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.position import Position

NOW = datetime(2026, 8, 27, 12, tzinfo=UTC)


def test_stock_dividend_and_adr_ratio_adjust_views_without_rewriting_history() -> None:
    position = Position(Symbol("TSM"), Decimal("10"))
    processor = CorporateActionProcessor()
    actions = (
        StockDividend(uuid4(), Symbol("TSM"), NOW, NOW, Decimal("0.10")),
        AdrRatioChange(uuid4(), Symbol("TSM"), NOW, NOW, Decimal("2"), Decimal("1")),
    )

    result = processor.adjust_position_with_gaps(position, actions)

    assert result.position.quantity == Decimal("5.50")
    assert result.gaps == ()
    assert position.quantity == Decimal("10")


@pytest.mark.parametrize(
    "action_type",
    ["SPIN_OFF", "SYMBOL_CHANGE", "MERGER_ACQUISITION"],
)
def test_reference_actions_emit_explicit_gaps(action_type: str) -> None:
    action = ReferenceAction(uuid4(), Symbol("NVDA"), NOW, NOW, action_type, {"target": "FIXTURE"})

    result = CorporateActionProcessor().adjust_position_with_gaps(
        Position(Symbol("NVDA"), Decimal("10")), (action,)
    )

    assert result.position.quantity == Decimal("10")
    assert result.gaps[0].reason == "UNSUPPORTED_CORPORATE_ACTION"
    assert result.gaps[0].action_id == action.id


def test_cash_dividend_refuses_implicit_currency_conversion() -> None:
    action = CashDividend(uuid4(), Symbol("TSM"), NOW, NOW, Decimal("1"), "TWD")

    with pytest.raises(ValueError, match="implicit FX"):
        CorporateActionProcessor().apply_dividends(
            (), uuid4(), Position(Symbol("TSM"), Decimal("10")), (action,), cash_currency="USD"
        )
