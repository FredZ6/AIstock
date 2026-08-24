"""Idempotent seed for the approved eleven-security Watchlist."""

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from stock_platform.infrastructure.db.models.tables import (
    security,
    security_identifier_version,
    security_profile_version,
    watchlist_item,
)

SECURITY_MASTER_AVAILABLE_AT = datetime(2026, 8, 23, 10, 50, tzinfo=UTC)
SECURITY_MASTER: tuple[dict[str, Any], ...] = (
    {
        "symbol": "NVDA",
        "company_name": "NVIDIA",
        "exchange": "Nasdaq",
        "industry_role": "AI accelerator / Compute",
        "cik": "1045810",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "AVGO",
        "company_name": "Broadcom",
        "exchange": "Nasdaq",
        "industry_role": "ASIC / Networking",
        "cik": "1730168",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "TSM",
        "company_name": "TSMC ADR",
        "exchange": "NYSE",
        "industry_role": "Foundry",
        "cik": "1046179",
        "filing_regime": "FOREIGN_PRIVATE_ISSUER",
        "instrument_type": "ADR",
    },
    {
        "symbol": "SKHY",
        "company_name": "SK hynix ADR",
        "exchange": "Nasdaq",
        "industry_role": "HBM / DRAM / NAND",
        "cik": "2120882",
        "filing_regime": "FOREIGN_PRIVATE_ISSUER",
        "instrument_type": "ADR",
    },
    {
        "symbol": "WDC",
        "company_name": "Western Digital",
        "exchange": "Nasdaq",
        "industry_role": "HDD / Storage",
        "cik": "106040",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "SNDK",
        "company_name": "Sandisk",
        "exchange": "Nasdaq",
        "industry_role": "NAND / Flash",
        "cik": "2023554",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "MU",
        "company_name": "Micron",
        "exchange": "Nasdaq",
        "industry_role": "HBM / DRAM / NAND",
        "cik": "723125",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "NBIS",
        "company_name": "Nebius Group",
        "exchange": "Nasdaq",
        "industry_role": "AI Cloud",
        "cik": "1513845",
        "filing_regime": "FOREIGN_PRIVATE_ISSUER",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "MRVL",
        "company_name": "Marvell",
        "exchange": "Nasdaq",
        "industry_role": "Data-center silicon",
        "cik": "1835632",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "BE",
        "company_name": "Bloom Energy",
        "exchange": "NYSE",
        "industry_role": "Data-center power",
        "cik": "1664703",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
    {
        "symbol": "INTC",
        "company_name": "Intel",
        "exchange": "Nasdaq",
        "industry_role": "CPU / Foundry",
        "cik": "50863",
        "filing_regime": "US_DOMESTIC",
        "instrument_type": "COMMON_STOCK",
    },
)


def _stable_id(kind: str, symbol: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"aistock/{kind}/{symbol}")


def seed_security_master(connection: Connection) -> int:
    inserted_watchlist_items = 0
    for item in SECURITY_MASTER:
        symbol = str(item["symbol"])
        existing_identifier = (
            connection.execute(
                select(
                    security_identifier_version.c.id,
                    security_identifier_version.c.security_id,
                )
                .where(
                    security_identifier_version.c.identifier_type == "PRIMARY_SYMBOL",
                    security_identifier_version.c.identifier_value == symbol,
                )
                .order_by(security_identifier_version.c.available_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        security_id = (
            existing_identifier["security_id"]
            if existing_identifier is not None
            else _stable_id("security", symbol)
        )
        connection.execute(
            insert(security)
            .values(id=security_id, instrument_type=item["instrument_type"])
            .on_conflict_do_nothing(index_elements=[security.c.id])
        )
        identifier_id = _stable_id("security-identifier-v1", symbol)
        connection.execute(
            insert(security_identifier_version)
            .values(
                id=identifier_id,
                security_id=security_id,
                identifier_type="PRIMARY_SYMBOL",
                identifier_value=symbol,
                exchange=item["exchange"],
                provider_identifiers={"ALPACA": symbol, "ALPHA_VANTAGE": symbol},
                effective_from=SECURITY_MASTER_AVAILABLE_AT,
                available_at=SECURITY_MASTER_AVAILABLE_AT,
                supersedes_id=(
                    existing_identifier["id"]
                    if existing_identifier is not None
                    and existing_identifier["id"] != identifier_id
                    else None
                ),
            )
            .on_conflict_do_nothing(index_elements=[security_identifier_version.c.id])
        )
        previous_profile_id = connection.execute(
            select(security_profile_version.c.id)
            .where(security_profile_version.c.security_id == security_id)
            .order_by(security_profile_version.c.available_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        profile_id = _stable_id("security-profile-v1", symbol)
        connection.execute(
            insert(security_profile_version)
            .values(
                id=profile_id,
                security_id=security_id,
                company_name=item["company_name"],
                currency="USD",
                cik=item["cik"],
                filing_regime=item["filing_regime"],
                industry_role=item["industry_role"],
                exchange_timezone="America/New_York",
                is_adr=item["instrument_type"] == "ADR",
                effective_from=SECURITY_MASTER_AVAILABLE_AT,
                available_at=SECURITY_MASTER_AVAILABLE_AT,
                supersedes_id=(previous_profile_id if previous_profile_id != profile_id else None),
            )
            .on_conflict_do_nothing(index_elements=[security_profile_version.c.id])
        )
        inserted = connection.execute(
            insert(watchlist_item)
            .values(security_id=security_id, symbol=symbol)
            .on_conflict_do_nothing(index_elements=[watchlist_item.c.symbol])
            .returning(watchlist_item.c.security_id)
        ).scalar_one_or_none()
        inserted_watchlist_items += int(inserted is not None)
    return inserted_watchlist_items
