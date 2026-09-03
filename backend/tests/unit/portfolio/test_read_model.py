from datetime import UTC, datetime
from decimal import Decimal

from stock_platform.application.portfolio.read_model import PositionFill, build_positions


def test_positions_use_decimal_weighted_average_and_current_persisted_price() -> None:
    fills = (
        PositionFill("NVDA", "BUY", Decimal("10"), Decimal("100")),
        PositionFill("NVDA", "BUY", Decimal("5"), Decimal("120")),
        PositionFill("NVDA", "SELL", Decimal("3"), Decimal("130")),
    )
    available_at = datetime(2026, 9, 1, 1, tzinfo=UTC)

    positions = build_positions(
        fills,
        prices={"NVDA": (Decimal("110"), available_at)},
    )

    assert len(positions) == 1
    assert positions[0].symbol == "NVDA"
    assert positions[0].quantity == Decimal("12")
    assert positions[0].average_cost == Decimal("106.6666666666666666666666667")
    assert positions[0].market_price == Decimal("110")
    assert positions[0].market_value == Decimal("1320")
    assert positions[0].unrealized_pnl == Decimal("39.9999999999999999999999996")
    assert positions[0].price_available_at == available_at


def test_closed_positions_and_unpriced_positions_remain_explicit() -> None:
    fills = (
        PositionFill("MSFT", "BUY", Decimal("2"), Decimal("50")),
        PositionFill("MSFT", "SELL", Decimal("2"), Decimal("60")),
        PositionFill("AVGO", "BUY", Decimal("1"), Decimal("300")),
    )

    positions = build_positions(fills, prices={})

    assert [position.symbol for position in positions] == ["AVGO"]
    assert positions[0].average_cost == Decimal("300")
    assert positions[0].market_price is None
    assert positions[0].market_value is None
    assert positions[0].unrealized_pnl is None
