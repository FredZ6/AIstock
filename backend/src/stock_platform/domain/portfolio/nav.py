from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.portfolio.fill import PaperFill
from stock_platform.domain.portfolio.ledger import LedgerEntry, cash_balance
from stock_platform.domain.portfolio.position import rebuild_positions


@dataclass(frozen=True, slots=True)
class PortfolioNav:
    cash: Decimal
    positions_value: Decimal
    total: Decimal


def rebuild_nav(
    entries: Sequence[LedgerEntry],
    fills: Sequence[PaperFill],
    *,
    prices: Mapping[Symbol, Decimal],
    as_of: datetime,
) -> PortfolioNav:
    cutoff = require_aware(as_of)
    visible_entries = tuple(entry for entry in entries if entry.occurred_at <= cutoff)
    visible_fills = tuple(fill for fill in fills if fill.filled_at <= cutoff)
    if not visible_entries:
        raise ValueError("at least one ledger entry is required")
    portfolio_id = visible_entries[0].portfolio_id
    currencies = {entry.currency for entry in visible_entries}
    if len(currencies) != 1:
        raise ValueError("NAV requires one currency")
    if any(entry.portfolio_id != portfolio_id for entry in visible_entries):
        raise ValueError("NAV requires one portfolio")
    for value in prices.values():
        if not isinstance(value, Decimal):
            raise TypeError("prices must use Decimal")
    cash = cash_balance(visible_entries, portfolio_id, next(iter(currencies)))
    positions = rebuild_positions(visible_fills)
    positions_value = sum(
        (position.quantity * prices[position.symbol] for position in positions.values()),
        Decimal("0"),
    )
    return PortfolioNav(cash=cash, positions_value=positions_value, total=cash + positions_value)
