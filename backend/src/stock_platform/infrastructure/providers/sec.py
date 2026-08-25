"""Read-only SEC EDGAR transport and point-in-time identity resolution."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import Connection, or_, select

from stock_platform.domain.common.ids import Symbol
from stock_platform.domain.common.time import require_aware
from stock_platform.infrastructure.db.models.tables import (
    security_identifier_version,
    security_profile_version,
)
from stock_platform.infrastructure.providers.base import (
    FeedType,
    GovernedHttpProvider,
    ProviderBatch,
)


class SecFilingRegime(StrEnum):
    US_DOMESTIC = "US_DOMESTIC"
    FOREIGN_PRIVATE_ISSUER = "FOREIGN_PRIVATE_ISSUER"


@dataclass(frozen=True, slots=True)
class SecIdentity:
    symbol: Symbol
    cik: str
    regime: SecFilingRegime

    def __post_init__(self) -> None:
        normalized_cik = self.cik.removeprefix("CIK").zfill(10)
        if not normalized_cik.isdigit() or len(normalized_cik) != 10:
            raise ValueError("SEC CIK must contain at most ten digits")
        object.__setattr__(self, "cik", normalized_cik)


class SecIdentityResolver(Protocol):
    def resolve(self, symbol: Symbol, as_of: datetime) -> SecIdentity | None: ...


class StaticSecIdentityResolver:
    def __init__(self, identities: Mapping[Symbol, SecIdentity]) -> None:
        self._identities = dict(identities)

    def resolve(self, symbol: Symbol, as_of: datetime) -> SecIdentity | None:
        require_aware(as_of)
        return self._identities.get(symbol)


class PostgresSecIdentityResolver:
    """Resolve the latest Security master identity visible at the query cutoff."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def resolve(self, symbol: Symbol, as_of: datetime) -> SecIdentity | None:
        cutoff = require_aware(as_of)
        row = (
            self._connection.execute(
                select(
                    security_identifier_version.c.identifier_value,
                    security_profile_version.c.cik,
                    security_profile_version.c.filing_regime,
                )
                .join(
                    security_profile_version,
                    security_profile_version.c.security_id
                    == security_identifier_version.c.security_id,
                )
                .where(
                    security_identifier_version.c.identifier_type == "PRIMARY_SYMBOL",
                    security_identifier_version.c.identifier_value == str(symbol),
                    security_identifier_version.c.available_at <= cutoff,
                    security_identifier_version.c.effective_from <= cutoff,
                    or_(
                        security_identifier_version.c.effective_to.is_(None),
                        security_identifier_version.c.effective_to > cutoff,
                    ),
                    security_profile_version.c.available_at <= cutoff,
                    security_profile_version.c.effective_from <= cutoff,
                    or_(
                        security_profile_version.c.effective_to.is_(None),
                        security_profile_version.c.effective_to > cutoff,
                    ),
                    security_profile_version.c.cik.is_not(None),
                    security_profile_version.c.filing_regime.is_not(None),
                )
                .order_by(
                    security_profile_version.c.available_at.desc(),
                    security_identifier_version.c.available_at.desc(),
                )
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return SecIdentity(
            symbol=Symbol(str(row["identifier_value"])),
            cik=str(row["cik"]),
            regime=SecFilingRegime(str(row["filing_regime"])),
        )


_COMMON_PROSPECTUS_FORMS = frozenset({"424B1", "424B2", "424B3", "424B4", "424B5"})
_FORMS_BY_REGIME = {
    SecFilingRegime.US_DOMESTIC: frozenset(
        {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "DEF 14A", "S-1", "S-1/A"}
    )
    | _COMMON_PROSPECTUS_FORMS,
    SecFilingRegime.FOREIGN_PRIVATE_ISSUER: frozenset(
        {"20-F", "20-F/A", "6-K", "6-K/A", "F-1", "F-1/A"}
    )
    | _COMMON_PROSPECTUS_FORMS,
}


def allowed_sec_forms(regime: SecFilingRegime) -> frozenset[str]:
    return _FORMS_BY_REGIME[regime]


class SecRequestLimiter:
    """Thread-safe sliding-window limiter shared by SEC adapter instances."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        requests_per_second: int = 5,
    ) -> None:
        if requests_per_second < 1 or requests_per_second > 5:
            raise ValueError("SEC request limit must be in [1, 5]")
        self._clock = clock
        self._sleep = sleep
        self._limit = requests_per_second
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            while self._timestamps and self._timestamps[0] <= now - 1.0:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._limit:
                self._sleep(max(0.0, 1.0 - (now - self._timestamps[0])))
                now = self._clock()
                while self._timestamps and self._timestamps[0] <= now - 1.0:
                    self._timestamps.popleft()
            self._timestamps.append(now)


def _seeded_identity_resolver() -> StaticSecIdentityResolver:
    from stock_platform.infrastructure.db.security_seed import SECURITY_MASTER

    return StaticSecIdentityResolver(
        {
            Symbol(str(item["symbol"])): SecIdentity(
                symbol=Symbol(str(item["symbol"])),
                cik=str(item["cik"]),
                regime=SecFilingRegime(str(item["filing_regime"])),
            )
            for item in SECURITY_MASTER
        }
    )


_GLOBAL_LIMITER = SecRequestLimiter()
_USER_AGENT = re.compile(r"^[A-Za-z0-9._-]+/[^\s]+\s+[^\s@]+@[^\s@]+$")
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_DOCUMENT = re.compile(r"^[A-Za-z0-9._-]+$")


class SecProvider(GovernedHttpProvider):
    name = "SEC"
    supported_feeds = frozenset({FeedType.COMPANY_FACTS, FeedType.FILINGS})

    def __init__(
        self,
        *,
        user_agent: str | None,
        identity_resolver: SecIdentityResolver | None = None,
        limiter: SecRequestLimiter | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._user_agent = user_agent
        self._identity_resolver = identity_resolver or _seeded_identity_resolver()
        self._limiter = limiter or _GLOBAL_LIMITER

    @property
    def configured(self) -> bool:
        return self._configured()

    def _configured(self) -> bool:
        return bool(self._user_agent and _USER_AGENT.fullmatch(self._user_agent))

    def _headers(self) -> dict[str, str]:
        return super()._headers() | {"User-Agent": self._user_agent or ""}

    def _identity(self, symbol: Symbol, as_of: datetime) -> SecIdentity | None:
        return self._identity_resolver.resolve(symbol, require_aware(as_of))

    def _supports_symbol(self, symbol: Symbol) -> bool:
        return self._identity(symbol, require_aware(self._clock())) is not None

    def _url(self, feed_type: FeedType, symbol: Symbol, as_of: datetime) -> str:
        identity = self._identity(symbol, as_of)
        if identity is None:
            raise ValueError(f"unknown SEC Security identity: {symbol}")
        if feed_type is FeedType.COMPANY_FACTS:
            return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{identity.cik}.json"
        if feed_type is FeedType.FILINGS:
            return f"https://data.sec.gov/submissions/CIK{identity.cik}.json"
        raise ValueError(f"unsupported SEC feed: {feed_type.value}")

    def _fetch_batch_from_url(
        self,
        *,
        feed_type: FeedType,
        symbol: Symbol,
        query_as_of: datetime,
        url: str,
    ) -> ProviderBatch:
        self._limiter.acquire()
        return super()._fetch_batch_from_url(
            feed_type=feed_type,
            symbol=symbol,
            query_as_of=query_as_of,
            url=url,
        )

    def fetch_filing_document(
        self,
        symbol: str,
        *,
        accession_number: str,
        primary_document: str,
        as_of: datetime,
    ) -> ProviderBatch:
        query_as_of = require_aware(as_of)
        normalized_symbol = Symbol(symbol)
        identity = self._identity(normalized_symbol, query_as_of)
        if identity is None:
            raise ValueError(f"unknown SEC Security identity: {symbol}")
        if not self._configured():
            raise ValueError("SEC User-Agent requires application/version and contact")
        if not _ACCESSION.fullmatch(accession_number):
            raise ValueError("invalid SEC accession number")
        if not _DOCUMENT.fullmatch(primary_document):
            raise ValueError("invalid SEC primary document name")
        accession_path = accession_number.replace("-", "")
        cik_path = str(int(identity.cik))
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_path}/"
            f"{accession_path}/{primary_document}"
        )
        return self._fetch_batch_from_url(
            feed_type=FeedType.FILINGS,
            symbol=normalized_symbol,
            query_as_of=query_as_of,
            url=url,
        )
