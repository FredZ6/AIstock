"""Narrow tool authorization independent of model or retrieved content."""

from __future__ import annotations

from collections.abc import Mapping

from stock_platform.domain.common.errors import ToolPolicyDenied

_FORBIDDEN_ARGUMENTS = frozenset({"url", "sql", "python", "shell", "api_key", "command"})


class ToolPolicyGateway:
    def __init__(self, allowed_tools: frozenset[str]) -> None:
        self._allowed_tools = allowed_tools

    def authorize(self, tool_name: str, arguments: Mapping[str, object]) -> None:
        if tool_name not in self._allowed_tools:
            raise ToolPolicyDenied(f"tool not allowed: {tool_name}")
        forbidden = _FORBIDDEN_ARGUMENTS.intersection(key.lower() for key in arguments)
        if forbidden:
            raise ToolPolicyDenied(f"forbidden tool arguments: {', '.join(sorted(forbidden))}")
