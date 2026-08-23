"""Central recursive redaction for logs, traces, events, and error metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = (
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "access_key",
    "prompt",
    "email",
    "recipient",
    "notification_address",
    "provider_payload",
    "raw_text",
    "full_text",
    "private_key",
)
_SENSITIVE_EXACT_KEYS = frozenset({"key"})


def _sensitive_key(key: object) -> bool:
    normalized = str(key).lower()
    return normalized in _SENSITIVE_EXACT_KEYS or any(
        fragment in normalized for fragment in _SENSITIVE_KEYS
    )


def redact(value: Any) -> Any:
    """Return a recursively redacted copy suitable for operational telemetry."""

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str) and value.lower().startswith("bearer "):
        return REDACTED
    return value
