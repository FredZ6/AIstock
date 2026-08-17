from decimal import Decimal
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from stock_platform.domain.common.errors import CurrencyMismatch
from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.money import Money


def test_money_preserves_decimal_cents() -> None:
    amount = Money(amount=Decimal("10.01"), currency="USD")
    assert amount.amount == Decimal("10.01")


def test_money_rejects_binary_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        Money(amount=cast(Any, 10.01), currency="USD")


def test_different_currencies_cannot_be_added() -> None:
    with pytest.raises(CurrencyMismatch):
        Money(amount=Decimal("10.00"), currency="USD") + Money(
            amount=Decimal("5.00"), currency="CNY"
        )


@given(
    left=st.decimals(allow_nan=False, allow_infinity=False, places=4),
    right=st.decimals(allow_nan=False, allow_infinity=False, places=4),
)
def test_same_currency_addition_is_exact(left: Decimal, right: Decimal) -> None:
    result = Money(amount=left, currency="USD") + Money(amount=right, currency="USD")
    assert result.amount == left + right
    assert result.currency == "USD"


@pytest.mark.parametrize(("raw", "expected"), [("nvda", "NVDA"), ("brk.b", "BRK.B")])
def test_symbol_is_normalized(raw: str, expected: str) -> None:
    assert str(Symbol(raw)) == expected


@pytest.mark.parametrize("raw", ["", "TOO-LONG-SYMBOL", "BTC/USD", "A B"])
def test_invalid_symbol_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        Symbol(raw)
