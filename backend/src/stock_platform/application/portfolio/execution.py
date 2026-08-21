from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid5

from stock_platform.domain.portfolio.fill import ExecutionBar, PaperFill
from stock_platform.domain.portfolio.order import OrderIntent, OrderSide

_BPS = Decimal("10000")
_FILL_NAMESPACE = UUID("9d1ac474-0f57-45d9-a942-1f2b1b8743cb")


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    id: UUID
    version: str
    spread_bps: Decimal
    slippage_bps: Decimal
    fee_per_share: Decimal
    minimum_fee: Decimal
    volume_participation: Decimal

    def __post_init__(self) -> None:
        for name in (
            "spread_bps",
            "slippage_bps",
            "fee_per_share",
            "minimum_fee",
            "volume_participation",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must use Decimal")
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.volume_participation <= 0 or self.volume_participation > 1:
            raise ValueError("volume_participation must be in (0, 1]")
        if not self.version:
            raise ValueError("execution policy version is required")


class PaperExecutionSimulator:
    def __init__(self, policy: ExecutionPolicy) -> None:
        self.policy = policy

    def execute(
        self,
        order: OrderIntent,
        bars: Sequence[ExecutionBar],
        *,
        prior_fills: Sequence[PaperFill] = (),
    ) -> tuple[PaperFill, ...]:
        if not order.risk_approved:
            return ()
        if order.execution_policy_version_id != self.policy.id:
            raise ValueError("order and execution policy version do not match")

        revisions: dict[tuple[str, object], ExecutionBar] = {}
        for item in bars:
            key = (str(item.symbol), item.event_time)
            current = revisions.get(key)
            if (
                current is not None
                and (
                    item.available_at,
                    item.content_hash,
                )
                == (current.available_at, current.content_hash)
                and (
                    item.open,
                    item.volume,
                )
                != (current.open, current.volume)
            ):
                raise ValueError("conflicting bars share a revision identity")
            if current is None or (item.available_at, item.content_hash) > (
                current.available_at,
                current.content_hash,
            ):
                revisions[key] = item
        eligible = sorted(
            (
                item
                for item in revisions.values()
                if item.symbol == order.symbol and item.event_time > order.decision_time
            ),
            key=lambda item: (item.event_time, item.available_at),
        )
        unique_prior = tuple({item.id: item for item in prior_fills}.values())
        if any(
            item.order_id != order.id
            or item.portfolio_id != order.portfolio_id
            or item.symbol != order.symbol
            or item.execution_policy_version_id != self.policy.id
            or item.reversal_of_id is not None
            for item in unique_prior
        ):
            raise ValueError("prior fills do not belong to the order")
        previously_filled = sum((item.quantity for item in unique_prior), Decimal("0"))
        if previously_filled > order.quantity:
            raise ValueError("prior fills exceed order quantity")
        consumed_revisions = {(item.source_bar_time, item.filled_at) for item in unique_prior}
        remaining = order.quantity - previously_filled
        fills: list[PaperFill] = []
        for item in eligible:
            if (item.event_time, item.available_at) in consumed_revisions:
                continue
            available = item.volume * self.policy.volume_participation
            quantity = min(remaining, available)
            if quantity <= 0:
                continue
            price_adjustment = (
                self.policy.spread_bps / Decimal("2") + self.policy.slippage_bps
            ) / _BPS
            multiplier = (
                Decimal("1") + price_adjustment
                if order.side == OrderSide.BUY
                else Decimal("1") - price_adjustment
            )
            price = item.open * multiplier
            fee = max(self.policy.minimum_fee, self.policy.fee_per_share * quantity)
            identity = "|".join(
                (
                    str(order.id),
                    item.event_time.isoformat(),
                    item.available_at.isoformat(),
                    item.content_hash,
                    str(quantity),
                    str(self.policy.id),
                )
            )
            fills.append(
                PaperFill(
                    id=uuid5(_FILL_NAMESPACE, identity),
                    order_id=order.id,
                    portfolio_id=order.portfolio_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=quantity,
                    price=price,
                    fee=fee,
                    currency="USD",
                    filled_at=item.available_at,
                    source_bar_time=item.event_time,
                    execution_policy_version_id=self.policy.id,
                )
            )
            remaining -= quantity
            if remaining == 0:
                break
        return tuple(fills)
