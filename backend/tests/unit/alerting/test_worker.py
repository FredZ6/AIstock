from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from stock_platform.application.alerting.features import MinuteBar
from stock_platform.application.alerting.outbox import AlertContext, NotificationChannel
from stock_platform.application.alerting.rules import AlertRule
from stock_platform.domain.common.ids import Symbol
from stock_platform.infrastructure.messaging.market_stream import StreamMessage
from stock_platform.workers.alert_worker import AlertWorker, ExplanationStatus

START = datetime(2026, 8, 20, 14, 30, tzinfo=UTC)


def bars() -> tuple[MinuteBar, ...]:
    closes = ("100", "100.2", "99.9", "100.3", "100.1", "106")
    volumes = ("100", "110", "90", "105", "95", "600")
    result = []
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        event_time = START + timedelta(minutes=index)
        result.append(
            MinuteBar(
                symbol=Symbol("NVDA"),
                event_time=event_time,
                available_at=event_time + timedelta(seconds=1),
                ingested_at=event_time + timedelta(seconds=2),
                open=Decimal("100"),
                high=Decimal(close) + Decimal("0.2"),
                low=Decimal("99.8"),
                close=Decimal(close),
                volume=Decimal(volume),
                previous_close=Decimal("99"),
                provider="ALPACA",
                content_hash=f"{index:064x}",
                raw_object_key=f"fixture/{index}.json",
                raw_payload={"index": index},
            )
        )
    return tuple(result)


class RecordingStream:
    def __init__(self) -> None:
        self.acked: list[tuple[str, str]] = []

    def acknowledge(self, *, group: str, message_id: str) -> None:
        self.acked.append((group, message_id))


class FailingStore:
    def persist_bar(self, item: MinuteBar) -> bool:
        raise RuntimeError("database unavailable")


def test_stream_is_not_acknowledged_when_durable_persistence_fails() -> None:
    stream = RecordingStream()
    worker = AlertWorker(
        stream=stream,
        store=FailingStore(),  # type: ignore[arg-type]
        rule=AlertRule.default(minimum_conditions=2),
        context_resolver=lambda _symbol, _time: AlertContext(uuid4(), None, None),
        explainer=None,
        channels=(NotificationChannel.TELEGRAM,),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        worker.process(StreamMessage("1-0", bars()[-1]), group="alerts")

    assert stream.acked == []


class RecordingStore:
    def __init__(self, history: tuple[MinuteBar, ...]) -> None:
        self.history = history
        self.alert_ids: list[UUID] = []
        self.explanations: list[tuple[UUID, ExplanationStatus, str | None]] = []

    def persist_bar(self, item: MinuteBar) -> bool:
        return True

    def recent_bars(self, *, symbol: str, through: datetime, limit: int) -> tuple[MinuteBar, ...]:
        return self.history[-limit:]

    def persist_alert(self, **values: object) -> bool:
        self.alert_ids.append(cast(UUID, values["alert_id"]))
        return True

    def record_explanation(
        self,
        *,
        alert_id: UUID,
        status: ExplanationStatus,
        content: str | None,
        error_code: str | None,
    ) -> None:
        self.explanations.append((alert_id, status, error_code))


class TimeoutExplainer:
    def explain(self, **_values: object) -> str:
        raise TimeoutError("explanation exceeded budget")


def test_explanation_timeout_is_visible_but_alert_is_persisted_and_acked() -> None:
    history = bars()
    stream = RecordingStream()
    store = RecordingStore(history)
    worker = AlertWorker(
        stream=stream,
        store=store,
        rule=AlertRule.default(minimum_conditions=2),
        context_resolver=lambda _symbol, _time: AlertContext(uuid4(), "Breakout invalidated", None),
        explainer=TimeoutExplainer(),
        channels=(NotificationChannel.TELEGRAM,),
    )

    result = worker.process(StreamMessage("7-0", history[-1]), group="alerts")

    assert result.alert_id is not None
    assert store.alert_ids == [result.alert_id]
    assert store.explanations == [(result.alert_id, ExplanationStatus.FAILED, "TIMEOUT")]
    assert stream.acked == [("alerts", "7-0")]
