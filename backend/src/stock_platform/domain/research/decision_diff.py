from collections.abc import Mapping
from typing import Any


def build_decision_diff(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        field: {"before": previous.get(field), "after": current.get(field)}
        for field in sorted(previous.keys() | current.keys())
        if previous.get(field) != current.get(field)
    }
