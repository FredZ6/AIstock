import re
from dataclasses import dataclass
from decimal import Decimal

from stock_platform.domain.common.errors import CurrencyMismatch

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be a Decimal")
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
        normalized_currency = self.currency.upper()
        if not _CURRENCY_PATTERN.fullmatch(normalized_currency):
            raise ValueError("currency must be a three-letter ISO code")
        object.__setattr__(self, "currency", normalized_currency)

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise CurrencyMismatch(f"cannot add {self.currency} and {other.currency}")
        return Money(amount=self.amount + other.amount, currency=self.currency)
