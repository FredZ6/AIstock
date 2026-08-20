from datetime import UTC, datetime
from uuid import uuid4

from stock_platform.application.alerting.outbox import (
    DeliveryStatus,
    InMemoryOutboxStore,
    NotificationChannel,
    OutboxDispatcher,
    OutboxMessage,
)


class RecordingAdapter:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[dict[str, object]] = []

    def send(self, payload: dict[str, object]) -> None:
        self.calls.append(payload)
        if self.fail_first and len(self.calls) == 1:
            raise TimeoutError("fixture timeout")


def test_one_outbox_message_retries_only_failed_channel_without_duplication() -> None:
    now = datetime(2026, 8, 20, 14, 40, tzinfo=UTC)
    message = OutboxMessage.create(
        alert_id=uuid4(),
        alert_key="NVDA:market-anomaly-v1:2026-08-20T14:30:00Z",
        payload={"symbol": "NVDA", "kind": "DETERMINISTIC_ALERT"},
        channels=(NotificationChannel.TELEGRAM, NotificationChannel.FEISHU),
        created_at=now,
    )
    store = InMemoryOutboxStore((message,))
    telegram = RecordingAdapter()
    feishu = RecordingAdapter(fail_first=True)
    dispatcher = OutboxDispatcher(
        store=store,
        adapters={
            NotificationChannel.TELEGRAM: telegram,
            NotificationChannel.FEISHU: feishu,
        },
        clock=lambda: now,
    )

    dispatcher.dispatch_due()
    first = store.get(message.id)
    assert first.status is DeliveryStatus.RETRY
    assert first.attempts == 1
    assert len(store.all()) == 1
    assert len(telegram.calls) == 1
    assert len(feishu.calls) == 1

    dispatcher.dispatch_due()
    delivered = store.get(message.id)
    assert delivered.status is DeliveryStatus.DELIVERED
    assert delivered.attempts == 2
    assert len(store.all()) == 1
    assert len(telegram.calls) == 1
    assert len(feishu.calls) == 2


def test_missing_channel_adapter_is_a_visible_retry_not_a_dropped_message() -> None:
    now = datetime(2026, 8, 20, 14, 40, tzinfo=UTC)
    message = OutboxMessage.create(
        alert_id=uuid4(),
        alert_key="NVDA:market-anomaly-v1:2026-08-20T14:30:00Z",
        payload={"symbol": "NVDA"},
        channels=(NotificationChannel.EMAIL,),
        created_at=now,
    )
    store = InMemoryOutboxStore((message,))

    OutboxDispatcher(store=store, adapters={}, clock=lambda: now).dispatch_due()

    retried = store.get(message.id)
    assert retried.status is DeliveryStatus.RETRY
    assert retried.channel_states[NotificationChannel.EMAIL].last_error == "ADAPTER_UNAVAILABLE"
