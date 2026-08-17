import re
from typing import NewType
from uuid import UUID

_SYMBOL_PATTERN = re.compile(r"^[A-Z.]{1,10}$")


class Symbol(str):
    def __new__(cls, value: str) -> "Symbol":
        normalized = value.upper()
        if not _SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("symbol must match [A-Z.]{1,10}")
        return super().__new__(cls, normalized)


RunId = NewType("RunId", UUID)
EvidenceId = NewType("EvidenceId", UUID)
ClaimId = NewType("ClaimId", UUID)
ThesisId = NewType("ThesisId", UUID)
DecisionId = NewType("DecisionId", UUID)
