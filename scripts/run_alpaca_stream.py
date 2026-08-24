#!/usr/bin/env python3
"""Run the paper-only Alpaca data stream supervisor (never a brokerage connection)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from stock_platform.application.market_data.policy import alpaca_entitlement_from_settings
from stock_platform.domain.ingestion.models import MarketDataCoverage
from stock_platform.infrastructure.db.models.tables import watchlist_item
from stock_platform.infrastructure.providers.object_store import MinioRawObjectStore
from stock_platform.settings import Settings
from stock_platform.workers.alpaca_stream_supervisor import AlpacaStreamSupervisor
from stock_platform.workers.celery_app import celery_app


def main() -> None:
    settings = Settings()
    entitlement = alpaca_entitlement_from_settings(
        settings,
        observed_at=datetime.now(UTC),
    )
    if entitlement is None:
        raise SystemExit("explicit Alpaca credentials and entitlement are required")
    coverage = (
        MarketDataCoverage.SIP
        if MarketDataCoverage.SIP in entitlement.coverage
        else MarketDataCoverage.IEX
    )
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            symbols = tuple(
                connection.execute(
                    select(watchlist_item.c.symbol).where(
                        watchlist_item.c.intraday_monitoring.is_(True)
                    )
                ).scalars()
            )
    finally:
        engine.dispose()
    raw_store = MinioRawObjectStore.from_settings(settings)

    def publish(task: str, args: list[str]) -> None:
        celery_app.send_task(task, args=args)

    celery_app.send_task(
        "stock_platform.workers.ingestion_tasks.reconcile_alpaca_stream_archive",
        args=[None],
        queue="ingestion-low",
    )
    supervisor = AlpacaStreamSupervisor(
        data_key=settings.alpaca_data_key or "",
        data_secret=settings.alpaca_data_secret or "",
        coverage=coverage,
        symbols=symbols,
        archive=lambda key, raw: raw_store.put(key, raw, "application/json"),
        publish=publish,
    )
    asyncio.run(supervisor.run_forever())


if __name__ == "__main__":
    main()
