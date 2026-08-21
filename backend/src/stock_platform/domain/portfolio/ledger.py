from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from stock_platform.domain.common.time import require_aware

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: UUID
    transaction_id: UUID
    portfolio_id: UUID
    source_id: UUID
    account: str
    debit: Decimal
    credit: Decimal
    currency: str
    occurred_at: datetime
    idempotency_key: str
    reversal_of_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.debit, Decimal) or not isinstance(self.credit, Decimal):
            raise TypeError("ledger amounts must use Decimal")
        if not self.debit.is_finite() or not self.credit.is_finite():
            raise ValueError("ledger amounts must be finite")
        if self.debit < ZERO or self.credit < ZERO:
            raise ValueError("ledger amounts cannot be negative")
        if (self.debit == ZERO) == (self.credit == ZERO):
            raise ValueError("exactly one of debit or credit must be positive")
        currency = self.currency.upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "occurred_at", require_aware(self.occurred_at).astimezone(UTC))


def is_balanced(entries: Sequence[LedgerEntry]) -> bool:
    totals: dict[tuple[UUID, str], list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for entry in {item.id: item for item in entries}.values():
        total = totals[(entry.transaction_id, entry.currency)]
        total[0] += entry.debit
        total[1] += entry.credit
    return all(debit == credit for debit, credit in totals.values())


def cash_balance(entries: Sequence[LedgerEntry], portfolio_id: UUID, currency: str) -> Decimal:
    normalized = currency.upper()
    return sum(
        (
            entry.debit - entry.credit
            for entry in {item.id: item for item in entries}.values()
            if entry.portfolio_id == portfolio_id
            and entry.currency == normalized
            and entry.account == "ASSET:CASH"
        ),
        ZERO,
    )
