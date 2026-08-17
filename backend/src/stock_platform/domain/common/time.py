from dataclasses import dataclass
from datetime import datetime


def require_aware(value: datetime) -> datetime:
    """Return a timestamp only when it has a usable UTC offset."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class PointInTimeRecord:
    event_time: datetime
    available_at: datetime
    ingested_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.event_time)
        require_aware(self.available_at)
        require_aware(self.ingested_at)
        if not self.event_time <= self.available_at <= self.ingested_at:
            raise ValueError("timestamps must satisfy event_time <= available_at <= ingested_at")

    def is_visible_at(self, decision_time: datetime) -> bool:
        return self.available_at <= require_aware(decision_time)
