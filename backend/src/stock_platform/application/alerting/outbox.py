"""Transactional alert persistence and retryable notification outbox."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, and_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping

from stock_platform.application.alerting.features import AnomalyFeatures, GapContext, MinuteBar
from stock_platform.application.alerting.rules import RuleEvaluation
from stock_platform.application.ingestion.normalizers.alpaca import market_session_for
from stock_platform.domain.common.time import require_aware
from stock_platform.domain.ingestion.models import MarketDataCoverage
from stock_platform.infrastructure.db.models.tables import (
    alert_event,
    alert_explanation,
    alert_metric,
    alert_thesis_link,
    derived_metric,
    evidence_item,
    investment_thesis,
    market_bar,
    normalized_record,
    notification_outbox,
    raw_data_object,
    thesis_evidence_link,
)
from stock_platform.infrastructure.observability.context import maybe_current_correlation
from stock_platform.infrastructure.observability.metrics import platform_metrics

_OUTBOX_NAMESPACE = UUID("4458e60a-ad59-420c-a71b-c2ca80e34a41")
_NEW_YORK = ZoneInfo("America/New_York")


class NotificationChannel(StrEnum):
    TELEGRAM = "TELEGRAM"
    FEISHU = "FEISHU"
    EMAIL = "EMAIL"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    RETRY = "RETRY"
    DELIVERED = "DELIVERED"


class BarPersistence(StrEnum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"


@dataclass(frozen=True, slots=True)
class AlertContext:
    thesis_id: UUID
    invalidation_condition: str | None
    evidence_id: UUID | None


class PostgresAlertContextResolver:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def __call__(self, symbol: str, decision_time: datetime) -> AlertContext:
        cutoff = require_aware(decision_time).astimezone(UTC)
        row = (
            self._connection.execute(
                select(
                    investment_thesis.c.id.label("thesis_id"),
                    investment_thesis.c.invalidation_conditions,
                    evidence_item.c.id.label("evidence_id"),
                )
                .select_from(
                    investment_thesis.join(
                        thesis_evidence_link,
                        thesis_evidence_link.c.thesis_id == investment_thesis.c.id,
                    )
                    .join(
                        evidence_item,
                        evidence_item.c.id == thesis_evidence_link.c.evidence_id,
                    )
                    .join(
                        derived_metric,
                        derived_metric.c.id == evidence_item.c.derived_metric_id,
                    )
                    .join(
                        normalized_record,
                        normalized_record.c.id == derived_metric.c.normalized_record_id,
                    )
                    .join(
                        raw_data_object,
                        raw_data_object.c.id == normalized_record.c.raw_data_object_id,
                    )
                )
                .where(
                    and_(
                        investment_thesis.c.symbol == symbol,
                        investment_thesis.c.as_of <= cutoff,
                        investment_thesis.c.created_at <= cutoff,
                        thesis_evidence_link.c.created_at <= cutoff,
                        evidence_item.c.created_at <= cutoff,
                        derived_metric.c.created_at <= cutoff,
                        normalized_record.c.created_at <= cutoff,
                        raw_data_object.c.available_at <= cutoff,
                        raw_data_object.c.created_at <= cutoff,
                    )
                )
                .order_by(
                    investment_thesis.c.as_of.desc(),
                    investment_thesis.c.created_at.desc(),
                    investment_thesis.c.id,
                    case(
                        (thesis_evidence_link.c.relation == "SUPPORTS", 0),
                        (thesis_evidence_link.c.relation == "CONTRADICTS", 1),
                        else_=2,
                    ),
                    thesis_evidence_link.c.weight.desc(),
                    evidence_item.c.id,
                )
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError(f"no cutoff-safe thesis evidence for {symbol}")
        invalidation_conditions = cast(list[object], row["invalidation_conditions"])
        invalidation = next(
            (str(item) for item in invalidation_conditions if str(item).strip()),
            None,
        )
        return AlertContext(
            thesis_id=cast(UUID, row["thesis_id"]),
            invalidation_condition=invalidation,
            evidence_id=cast(UUID, row["evidence_id"]),
        )


@dataclass(frozen=True, slots=True)
class ChannelState:
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    id: UUID
    alert_id: UUID
    alert_key: str
    payload: dict[str, object]
    channels: tuple[NotificationChannel, ...]
    channel_states: Mapping[NotificationChannel, ChannelState]
    status: DeliveryStatus
    attempts: int
    next_attempt_at: datetime
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        alert_id: UUID,
        alert_key: str,
        payload: dict[str, object],
        channels: tuple[NotificationChannel, ...],
        created_at: datetime,
    ) -> OutboxMessage:
        created = require_aware(created_at).astimezone(UTC)
        unique_channels = tuple(dict.fromkeys(channels))
        if not unique_channels:
            raise ValueError("at least one notification channel is required")
        return cls(
            id=uuid5(_OUTBOX_NAMESPACE, alert_key),
            alert_id=alert_id,
            alert_key=alert_key,
            payload=dict(payload),
            channels=unique_channels,
            channel_states={channel: ChannelState() for channel in unique_channels},
            status=DeliveryStatus.PENDING,
            attempts=0,
            next_attempt_at=created,
            last_error=None,
            delivered_at=None,
            created_at=created,
        )


class NotificationAdapter(Protocol):
    def send(self, payload: dict[str, object]) -> None: ...


class DeliveryStore(Protocol):
    def due(self, now: datetime) -> tuple[OutboxMessage, ...]: ...

    def save_delivery(self, message: OutboxMessage) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class InMemoryOutboxStore:
    def __init__(self, messages: Sequence[OutboxMessage] = ()) -> None:
        self._messages = {message.id: message for message in messages}

    def due(self, now: datetime) -> tuple[OutboxMessage, ...]:
        cutoff = require_aware(now)
        return tuple(
            message
            for message in self._messages.values()
            if message.status is not DeliveryStatus.DELIVERED and message.next_attempt_at <= cutoff
        )

    def save_delivery(self, message: OutboxMessage) -> None:
        self._messages[message.id] = message

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def get(self, message_id: UUID) -> OutboxMessage:
        return self._messages[message_id]

    def all(self) -> tuple[OutboxMessage, ...]:
        return tuple(self._messages.values())


class OutboxDispatcher:
    def __init__(
        self,
        *,
        store: DeliveryStore,
        adapters: Mapping[NotificationChannel, NotificationAdapter],
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._adapters = dict(adapters)
        self._clock = clock

    def dispatch_due(self) -> int:
        now = require_aware(self._clock()).astimezone(UTC)
        delivered = 0
        for message in self._store.due(now):
            states = dict(message.channel_states)
            errors: list[str] = []
            for channel in message.channels:
                current = states[channel]
                if current.status is DeliveryStatus.DELIVERED:
                    continue
                adapter = self._adapters.get(channel)
                if adapter is None:
                    error_code = "ADAPTER_UNAVAILABLE"
                    states[channel] = ChannelState(
                        DeliveryStatus.RETRY,
                        current.attempts + 1,
                        error_code,
                    )
                    errors.append(error_code)
                    continue
                try:
                    adapter.send(dict(message.payload))
                except TimeoutError:
                    error_code = "TIMEOUT"
                    states[channel] = ChannelState(
                        DeliveryStatus.RETRY,
                        current.attempts + 1,
                        error_code,
                    )
                    errors.append(error_code)
                except Exception:  # noqa: BLE001 - adapters are an isolation boundary
                    error_code = "DELIVERY_ERROR"
                    states[channel] = ChannelState(
                        DeliveryStatus.RETRY,
                        current.attempts + 1,
                        error_code,
                    )
                    errors.append(error_code)
                else:
                    states[channel] = ChannelState(
                        DeliveryStatus.DELIVERED,
                        current.attempts + 1,
                        None,
                    )
            complete = all(state.status is DeliveryStatus.DELIVERED for state in states.values())
            updated = replace(
                message,
                channel_states=states,
                status=DeliveryStatus.DELIVERED if complete else DeliveryStatus.RETRY,
                attempts=message.attempts + 1,
                next_attempt_at=now,
                last_error=errors[0] if errors else None,
                delivered_at=now if complete else None,
            )
            try:
                self._store.save_delivery(updated)
                self._store.commit()
            except Exception:
                self._store.rollback()
                raise
            delivered += int(complete)
        return delivered


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class PostgresAlertStore:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def persist_bar(self, item: MinuteBar) -> BarPersistence:
        existing = self.connection.execute(
            select(raw_data_object.c.id).where(
                and_(
                    raw_data_object.c.provider == item.provider,
                    raw_data_object.c.feed_type == "minute_bars_stream",
                    raw_data_object.c.content_hash == item.content_hash,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return BarPersistence.DUPLICATE
        latest = self.connection.execute(
            select(func.max(market_bar.c.event_time)).where(
                and_(
                    market_bar.c.symbol == str(item.symbol),
                    market_bar.c.feed_type == "minute_bars_stream",
                )
            )
        ).scalar_one_or_none()
        out_of_order = latest is not None and item.event_time < latest
        with self.connection.begin_nested():
            raw_id = cast(
                UUID,
                self.connection.execute(
                    pg_insert(raw_data_object)
                    .values(
                        provider=item.provider,
                        feed_type="minute_bars_stream",
                        event_time=item.event_time,
                        available_at=item.available_at,
                        ingested_at=item.ingested_at,
                        content_hash=item.content_hash,
                        raw_object_key=item.raw_object_key,
                    )
                    .returning(raw_data_object.c.id)
                ).scalar_one(),
            )
            normalized_id = cast(
                UUID,
                self.connection.execute(
                    pg_insert(normalized_record)
                    .values(
                        raw_data_object_id=raw_id,
                        record_type="market_bar",
                        record_key=f"{item.symbol}:{item.event_time.isoformat()}",
                        normalization_version="alpaca-stream-v1",
                        payload=_json_safe(item.raw_payload),
                    )
                    .returning(normalized_record.c.id)
                ).scalar_one(),
            )
            self.connection.execute(
                pg_insert(market_bar)
                .values(
                    id=uuid5(_OUTBOX_NAMESPACE, item.content_hash),
                    event_time=item.event_time,
                    symbol=str(item.symbol),
                    raw_data_object_id=raw_id,
                    normalized_record_id=normalized_id,
                    provider=item.provider,
                    feed_type="minute_bars_stream",
                    coverage=MarketDataCoverage.IEX.value,
                    session=market_session_for(item.event_time).value,
                    content_hash=item.content_hash,
                    raw_object_key=item.raw_object_key,
                    available_at=item.available_at,
                    ingested_at=item.ingested_at,
                    open=item.open,
                    high=item.high,
                    low=item.low,
                    close=item.close,
                    volume=item.volume,
                    previous_close=item.previous_close,
                    conflict=item.conflict,
                    payload=_json_safe(item.raw_payload),
                )
                .on_conflict_do_nothing()
            )
        return BarPersistence.OUT_OF_ORDER if out_of_order else BarPersistence.NEW

    def recent_bars(
        self,
        *,
        symbol: str,
        through: datetime,
        available_by: datetime,
        limit: int,
    ) -> tuple[MinuteBar, ...]:
        cutoff = require_aware(available_by)
        ranked = (
            select(
                *market_bar.c,
                func.row_number()
                .over(
                    partition_by=(
                        market_bar.c.symbol,
                        market_bar.c.feed_type,
                        market_bar.c.event_time,
                    ),
                    order_by=(
                        market_bar.c.available_at.desc(),
                        market_bar.c.ingested_at.desc(),
                        market_bar.c.content_hash.desc(),
                    ),
                )
                .label("revision_rank"),
            )
            .where(
                and_(
                    market_bar.c.symbol == symbol,
                    market_bar.c.feed_type == "minute_bars_stream",
                    market_bar.c.event_time <= require_aware(through),
                    market_bar.c.available_at <= cutoff,
                )
            )
            .subquery()
        )
        rows = self.connection.execute(
            select(ranked)
            .where(ranked.c.revision_rank == 1)
            .order_by(ranked.c.event_time.desc())
            .limit(limit)
        ).mappings()
        result = [
            MinuteBar(
                symbol=row["symbol"],
                event_time=row["event_time"],
                available_at=row["available_at"],
                ingested_at=row["ingested_at"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                previous_close=row["previous_close"],
                provider=row["provider"],
                content_hash=row["content_hash"],
                raw_object_key=row["raw_object_key"],
                raw_payload=row["payload"],
                conflict=row["conflict"],
            )
            for row in rows
        ]
        return tuple(reversed(result))

    def gap_context(
        self,
        *,
        symbol: str,
        through: datetime,
        available_by: datetime,
    ) -> GapContext | None:
        event_cutoff = require_aware(through).astimezone(UTC)
        availability_cutoff = require_aware(available_by).astimezone(UTC)
        session_date = event_cutoff.astimezone(_NEW_YORK).date()
        session_open = datetime.combine(session_date, time(9, 30), _NEW_YORK).astimezone(UTC)
        if event_cutoff < session_open:
            return None
        open_row = self.connection.execute(
            select(market_bar.c.open)
            .where(
                and_(
                    market_bar.c.symbol == symbol,
                    market_bar.c.feed_type == "minute_bars_stream",
                    market_bar.c.event_time == session_open,
                    market_bar.c.available_at <= availability_cutoff,
                )
            )
            .order_by(
                market_bar.c.available_at.desc(),
                market_bar.c.ingested_at.desc(),
                market_bar.c.content_hash.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if open_row is None:
            return None
        prior_closes = tuple(
            datetime.combine(
                session_date - timedelta(days=days), time(15, 59), _NEW_YORK
            ).astimezone(UTC)
            for days in range(1, 8)
        )
        previous_close = self.connection.execute(
            select(market_bar.c.close)
            .where(
                and_(
                    market_bar.c.symbol == symbol,
                    market_bar.c.feed_type == "minute_bars_stream",
                    market_bar.c.event_time.in_(prior_closes),
                    market_bar.c.available_at <= availability_cutoff,
                )
            )
            .order_by(
                market_bar.c.event_time.desc(),
                market_bar.c.available_at.desc(),
                market_bar.c.ingested_at.desc(),
                market_bar.c.content_hash.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if previous_close is None:
            return None
        return GapContext(session_open=open_row, previous_close=previous_close)

    def persist_alert(
        self,
        *,
        alert_id: UUID,
        alert_key: str,
        features: AnomalyFeatures,
        evaluation: RuleEvaluation,
        context: AlertContext,
        review_action: str,
        channels: tuple[NotificationChannel, ...],
    ) -> bool:
        metrics = features.metrics()
        quality = {
            "freshness_seconds": str(features.data_quality.freshness.total_seconds()),
            "coverage": str(features.data_quality.coverage),
            "provider": features.data_quality.provider,
            "delay_seconds": str(features.data_quality.delay.total_seconds()),
            "conflict": features.data_quality.conflict,
        }
        payload: dict[str, object] = {
            "product_boundary": "research signal for a paper portfolio",
            "alert_id": str(alert_id),
            "alert_key": alert_key,
            "symbol": str(features.symbol),
            "event_time": features.event_time.isoformat(),
            "severity": evaluation.severity.value,
            "materiality": str(evaluation.materiality),
            "conditions": list(evaluation.conditions),
            "metrics": metrics,
            "thesis_id": str(context.thesis_id),
            "invalidation_condition": context.invalidation_condition,
            "review_action": review_action,
        }
        outbox_message = OutboxMessage.create(
            alert_id=alert_id,
            alert_key=alert_key,
            payload=payload,
            channels=channels,
            created_at=features.event_time,
        )
        with self.connection.begin_nested():
            correlation = maybe_current_correlation()
            inserted = self.connection.execute(
                pg_insert(alert_event)
                .values(
                    id=alert_id,
                    correlation_id=(
                        correlation.correlation_id if correlation is not None else alert_id
                    ),
                    alert_key=alert_key,
                    symbol=str(features.symbol),
                    event_time=features.event_time,
                    rule_id=evaluation.rule_id,
                    rule_version=evaluation.rule_version,
                    severity=evaluation.severity.value,
                    materiality=evaluation.materiality,
                    conditions=list(evaluation.conditions),
                    metrics=metrics,
                    data_quality=quality,
                )
                .on_conflict_do_nothing(index_elements=[alert_event.c.alert_key])
                .returning(alert_event.c.id)
            ).scalar_one_or_none()
            self.connection.execute(
                pg_insert(alert_thesis_link)
                .values(
                    alert_event_id=alert_id,
                    thesis_id=context.thesis_id,
                    invalidation_condition=context.invalidation_condition,
                    severity=evaluation.severity.value,
                    materiality=evaluation.materiality,
                    evidence_id=context.evidence_id,
                    review_action=review_action,
                )
                .on_conflict_do_nothing()
            )
            numeric_metrics: dict[str, Decimal | None] = {
                "five_minute_return": features.five_minute_return,
                "relative_volume": features.relative_volume,
                "return_zscore": features.return_zscore,
                "volume_zscore": features.volume_zscore,
                "volatility_zscore": features.volatility_zscore,
                "gap": features.gap,
                "breakout": Decimal(int(features.breakout is True)),
            }
            for name, value in numeric_metrics.items():
                if value is None:
                    continue
                self.connection.execute(
                    pg_insert(alert_metric)
                    .values(
                        id=uuid5(alert_id, name),
                        event_time=features.event_time,
                        alert_id=alert_id,
                        symbol=str(features.symbol),
                        metric_name=name,
                        metric_value=value,
                        algorithm_version=evaluation.rule_version,
                        data_quality=quality,
                    )
                    .on_conflict_do_nothing()
                )
            channel_states = {
                channel.value: {
                    "status": state.status.value,
                    "attempts": state.attempts,
                    "last_error": state.last_error,
                }
                for channel, state in outbox_message.channel_states.items()
            }
            self.connection.execute(
                pg_insert(notification_outbox)
                .values(
                    id=outbox_message.id,
                    alert_id=alert_id,
                    alert_key=alert_key,
                    payload=payload,
                    channels=[channel.value for channel in channels],
                    channel_states=channel_states,
                    status=outbox_message.status.value,
                    attempts=0,
                    next_attempt_at=outbox_message.next_attempt_at,
                )
                .on_conflict_do_nothing(index_elements=[notification_outbox.c.alert_key])
            )
        if inserted is not None:
            platform_metrics.observe_alert(rule=evaluation.rule_id, outcome="created")
        return inserted is not None

    def record_explanation(
        self,
        *,
        alert_id: UUID,
        status: StrEnum,
        content: str | None,
        error_code: str | None,
    ) -> None:
        with self.connection.begin_nested():
            self.connection.execute(
                pg_insert(alert_explanation)
                .values(
                    alert_id=alert_id,
                    status=status.value,
                    content=content,
                    error_code=error_code,
                )
                .on_conflict_do_nothing(index_elements=[alert_explanation.c.alert_id])
            )

    def due(self, now: datetime) -> tuple[OutboxMessage, ...]:
        rows = self.connection.execute(
            select(notification_outbox)
            .where(
                and_(
                    notification_outbox.c.status.in_(("PENDING", "RETRY")),
                    notification_outbox.c.next_attempt_at <= require_aware(now),
                )
            )
            .order_by(notification_outbox.c.created_at)
            .with_for_update(skip_locked=True)
        ).mappings()
        return tuple(self._message_from_row(row) for row in rows)

    def _message_from_row(self, row: RowMapping) -> OutboxMessage:
        channels = tuple(NotificationChannel(item) for item in cast(list[str], row["channels"]))
        stored_states = cast(dict[str, dict[str, object]], row["channel_states"])
        states = {
            channel: ChannelState(
                status=DeliveryStatus(cast(str, stored_states[channel.value]["status"])),
                attempts=cast(int, stored_states[channel.value]["attempts"]),
                last_error=cast(str | None, stored_states[channel.value]["last_error"]),
            )
            for channel in channels
        }
        return OutboxMessage(
            id=cast(UUID, row["id"]),
            alert_id=cast(UUID, row["alert_id"]),
            alert_key=cast(str, row["alert_key"]),
            payload=cast(dict[str, object], row["payload"]),
            channels=channels,
            channel_states=states,
            status=DeliveryStatus(cast(str, row["status"])),
            attempts=cast(int, row["attempts"]),
            next_attempt_at=cast(datetime, row["next_attempt_at"]),
            last_error=cast(str | None, row["last_error"]),
            delivered_at=cast(datetime | None, row["delivered_at"]),
            created_at=cast(datetime, row["created_at"]),
        )

    def save_delivery(self, message: OutboxMessage) -> None:
        states = {
            channel.value: {
                "status": state.status.value,
                "attempts": state.attempts,
                "last_error": state.last_error,
            }
            for channel, state in message.channel_states.items()
        }
        with self.connection.begin_nested():
            self.connection.execute(
                update(notification_outbox)
                .where(notification_outbox.c.id == message.id)
                .values(
                    channel_states=states,
                    status=message.status.value,
                    attempts=message.attempts,
                    next_attempt_at=message.next_attempt_at,
                    last_error=message.last_error,
                    delivered_at=message.delivered_at,
                    updated_at=message.next_attempt_at,
                )
            )
