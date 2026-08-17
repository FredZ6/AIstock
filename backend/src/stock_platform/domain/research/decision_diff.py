from collections.abc import Mapping
from typing import Any


def build_decision_diff(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    missing = object()
    changes: dict[str, dict[str, Any]] = {}
    for field in sorted(previous.keys() | current.keys()):
        before = previous.get(field, missing)
        after = current.get(field, missing)
        if before is missing or after is missing or before != after:
            changes[field] = {
                "before": None if before is missing else before,
                "after": None if after is missing else after,
                "before_present": before is not missing,
                "after_present": after is not missing,
            }
    return changes
