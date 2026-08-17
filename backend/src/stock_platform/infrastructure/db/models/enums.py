from enum import StrEnum


class ThesisEvidenceRelation(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    CONTEXT = "CONTEXT"


class EvidenceGapKind(StrEnum):
    UNKNOWN = "UNKNOWN"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTED = "CONFLICTED"


class ResearchOpinionValue(StrEnum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    ABSTAIN = "ABSTAIN"


class PortfolioActionValue(StrEnum):
    ENTER = "ENTER"
    ADD = "ADD"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    NO_ACTION = "NO_ACTION"
