"""Deterministic completion checks over named invariants."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompletionResult:
    complete: bool
    missing: tuple[str, ...]


class CompletionVerifier:
    def verify(
        self,
        *,
        completed: frozenset[str],
        required: frozenset[str],
    ) -> CompletionResult:
        missing = tuple(sorted(required - completed))
        return CompletionResult(complete=not missing, missing=missing)
