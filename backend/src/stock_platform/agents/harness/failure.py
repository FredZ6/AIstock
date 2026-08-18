"""Stable failure categories for retries and audit."""

from enum import StrEnum

from stock_platform.domain.common.errors import ProviderUnavailable, ToolPolicyDenied


class FailureCategory(StrEnum):
    RETRYABLE = "RETRYABLE"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    POLICY_DENIED = "POLICY_DENIED"
    INTERNAL_DEFECT = "INTERNAL_DEFECT"


class FailureClassifier:
    def classify(self, error: Exception) -> FailureCategory:
        if isinstance(error, ProviderUnavailable | TimeoutError | ConnectionError):
            return FailureCategory.RETRYABLE
        if isinstance(error, ToolPolicyDenied | PermissionError):
            return FailureCategory.POLICY_DENIED
        if isinstance(error, ValueError | TypeError):
            return FailureCategory.INVALID_ARGUMENTS
        if isinstance(error, LookupError):
            return FailureCategory.INSUFFICIENT_EVIDENCE
        return FailureCategory.INTERNAL_DEFECT
