"""Central recursive redaction for logs, traces, events, and error metadata."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    if isinstance(value, str):
        if value.lower().startswith("bearer "):
            return REDACTED
        if value.startswith("{"):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                pass
            else:
                if (
                    isinstance(decoded, Mapping)
                    and str(decoded.get("action", "")).lower() == "auth"
                ):
                    return json.dumps(redact(decoded), separators=(",", ":"))
        parts = urlsplit(value)
        if parts.scheme and parts.netloc and parts.query:
            query = [
                (key, REDACTED if _sensitive_key(key) else item)
                for key, item in parse_qsl(parts.query, keep_blank_values=True)
            ]
            return urlunsplit(
                (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
            )
    return value
