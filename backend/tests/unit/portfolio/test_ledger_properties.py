from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_platform.application.portfolio.accounting import (
    apply_fill,
    initial_funding,
    reverse_fill,
)
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.ledger import cash_balance, is_balanced
from stock_platform.domain.portfolio.nav import rebuild_nav
from stock_platform.domain.portfolio.order import OrderSide

NOW = datetime(2026, 8, 21, 14, 35, tzinfo=UTC)
PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000001")
POLICY_ID = UUID("30000000-0000-0000-0000-000000000001")


def fill(
    number: int,
    *,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal,
    side: OrderSide = OrderSide.BUY,
) -> PaperFill:
    return PaperFill(
        id=UUID(int=number),
        order_id=UUID(int=1000 + number),
        portfolio_id=PORTFOLIO_ID,
        symbol=Symbol("NVDA"),
        side=side,
        quantity=quantity,
        price=price,
        fee=fee,
        currency="USD",
        filled_at=NOW + timedelta(seconds=number),
        source_bar_time=NOW,
        execution_policy_version_id=POLICY_ID,
    )


def test_fill_posts_balanced_entries_and_duplicate_delivery_is_idempotent() -> None:
    entries = initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", NOW)
    purchase = fill(1, quantity=Decimal("2"), price=Decimal("100"), fee=Decimal("1"))

    posted = apply_fill(entries, purchase)
    repeated = apply_fill(posted, purchase)

    assert is_balanced(posted)
    assert repeated == posted
    assert cash_balance(posted, PORTFOLIO_ID, "USD") == Decimal("799")


def test_insufficient_cash_cannot_create_a_negative_balance() -> None:
    entries = initial_funding(PORTFOLIO_ID, Decimal("100"), "USD", NOW)
    purchase = fill(1, quantity=Decimal("2"), price=Decimal("100"), fee=Decimal("1"))

    with pytest.raises(ValueError, match="negative cash"):
        apply_fill(entries, purchase)

    assert cash_balance(entries, PORTFOLIO_ID, "USD") == Decimal("100")


def test_reversal_entries_restore_cash_and_position_without_mutation() -> None:
    entries = initial_funding(PORTFOLIO_ID, Decimal("1000"), "USD", NOW)
    purchase = fill(1, quantity=Decimal("2"), price=Decimal("100"), fee=Decimal("1"))
    posted = apply_fill(entries, purchase)

    reversal, reversed_entries = reverse_fill(posted, purchase, occurred_at=NOW + timedelta(days=1))
    nav = rebuild_nav(
        reversed_entries,
        (purchase, reversal),
        prices={Symbol("NVDA"): Decimal("120")},
        as_of=NOW + timedelta(days=1, seconds=1),
    )

    assert purchase in (purchase, reversal)
    assert reversal.reversal_of_id == purchase.id
    assert is_balanced(reversed_entries)
    assert nav.cash == Decimal("1000")
    assert nav.positions_value == Decimal("0")
    assert nav.total == Decimal("1000")


@given(
    quantities=st.lists(
        st.integers(min_value=1, max_value=10).map(Decimal), min_size=1, max_size=10
    ),
    prices=st.lists(st.integers(min_value=1, max_value=100).map(Decimal), min_size=1, max_size=10),
)
def test_generated_fill_sequences_keep_debits_equal_credits_and_rebuild_nav(
    quantities: list[Decimal], prices: list[Decimal]
) -> None:
    pairs = list(zip(quantities, prices, strict=False))
    total_cost = sum((quantity * price for quantity, price in pairs), Decimal("0"))
    initial_cash = total_cost + Decimal(len(pairs)) + Decimal("100")
    entries = initial_funding(PORTFOLIO_ID, initial_cash, "USD", NOW)
    fills: list[PaperFill] = []
    for index, (quantity, price) in enumerate(pairs, start=1):
        item = fill(index, quantity=quantity, price=price, fee=Decimal("1"))
        fills.append(item)
        entries = apply_fill(entries, item)

    nav = rebuild_nav(
        entries,
        fills,
        prices={Symbol("NVDA"): prices[len(pairs) - 1]},
        as_of=NOW + timedelta(minutes=1),
    )

    expected_cash = initial_cash - total_cost - Decimal(len(pairs))
    expected_quantity = sum((quantity for quantity, _ in pairs), Decimal("0"))
    assert is_balanced(entries)
    assert nav.cash == expected_cash
    assert nav.positions_value == expected_quantity * prices[len(pairs) - 1]
    assert nav.total == nav.cash + nav.positions_value
