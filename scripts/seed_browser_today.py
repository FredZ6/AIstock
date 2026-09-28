"""Seed persisted Portfolio history for the isolated API browser acceptance."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import create_engine, insert
from stock_platform.application.portfolio.accounting import (
    PostgresPaperAccountingStore,
    initial_funding,
)
from stock_platform.infrastructure.db.models.tables import portfolio_nav

PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000001")


def seed(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            opened_at = datetime(2026, 9, 20, 20, tzinfo=UTC)
            PostgresPaperAccountingStore(connection).persist_ledger(
                initial_funding(PORTFOLIO_ID, Decimal("100000"), "USD", opened_at)
            )
            connection.execute(
                insert(portfolio_nav),
                [
                    {
                        "portfolio_id": PORTFOLIO_ID,
                        "nav": Decimal("100000.00"),
                        "event_time": opened_at,
                        "available_at": opened_at,
                    },
                    {
                        "portfolio_id": PORTFOLIO_ID,
                        "nav": Decimal("101250.00"),
                        "event_time": datetime(2026, 9, 21, 20, tzinfo=UTC),
                        "available_at": datetime(2026, 9, 21, 20, 1, tzinfo=UTC),
                    },
                    {
                        "portfolio_id": PORTFOLIO_ID,
                        "nav": Decimal("100800.00"),
                        "event_time": datetime(2026, 9, 22, 20, tzinfo=UTC),
                        "available_at": datetime(2026, 9, 22, 20, 1, tzinfo=UTC),
                    },
                ],
            )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    seed(args.database_url)


if __name__ == "__main__":
    main()
