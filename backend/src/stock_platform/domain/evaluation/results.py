"""Immutable evaluation verdicts shared by datasets and reports."""

from enum import StrEnum


class EvalVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ABSTAIN = "ABSTAIN"
