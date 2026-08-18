"""Context assembly that never promotes retrieved text into instructions."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

_INJECTION_PATTERN = re.compile(
    r"ignore (?:all |previous )?instructions|system:|system prompt|allowed_tools|"
    r"execute_order|send_notification|api[ _-]?key",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class UntrustedEvidence:
    text: str
    content_hash: str
    quarantined: bool


@dataclass(frozen=True, slots=True)
class AgentContext:
    trusted_instructions: tuple[str, ...]
    structured_facts: Mapping[str, object]
    retrieved_evidence: tuple[UntrustedEvidence, ...]
    prior_tool_results: tuple[Mapping[str, object], ...]


class ContextBuilder:
    def build(
        self,
        *,
        trusted_instructions: Sequence[str],
        structured_facts: Mapping[str, object],
        retrieved_evidence: Sequence[str],
        prior_tool_results: Sequence[Mapping[str, object]],
    ) -> AgentContext:
        evidence = tuple(
            UntrustedEvidence(
                text=text,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                quarantined=_INJECTION_PATTERN.search(text) is not None,
            )
            for text in retrieved_evidence
        )
        return AgentContext(
            trusted_instructions=tuple(trusted_instructions),
            structured_facts=MappingProxyType(dict(structured_facts)),
            retrieved_evidence=evidence,
            prior_tool_results=tuple(
                MappingProxyType(dict(result)) for result in prior_tool_results
            ),
        )
