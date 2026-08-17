class DomainError(Exception):
    """Base class for expected domain failures."""


class PointInTimeViolation(DomainError):
    """Raised when data was not available at a decision cutoff."""


class CurrencyMismatch(DomainError):
    """Raised when arithmetic mixes monetary currencies."""


class RiskRejected(DomainError):
    """Raised when a deterministic risk policy rejects an intent."""


class BudgetExceeded(DomainError):
    """Raised when a bounded execution budget is exhausted."""


class ToolPolicyDenied(DomainError):
    """Raised when a tool call violates its permission policy."""


class ProviderUnavailable(DomainError):
    """Raised when a required provider cannot serve a request."""
