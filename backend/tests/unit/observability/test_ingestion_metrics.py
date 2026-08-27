from stock_platform.infrastructure.observability.metrics import PlatformMetrics


def test_ingestion_metrics_cover_release_gate_signals_with_bounded_labels() -> None:
    metrics = PlatformMetrics()
    metrics.set_ingestion_job_lag(provider="ALPACA", dataset="price_bars", seconds=5)
    metrics.set_ingestion_job_lag(provider="ALPACA", dataset="price_bars", seconds=12)
    metrics.set_ingestion_state(provider="ALPACA", state="RUNNING", count=1)
    metrics.set_ingestion_cursor_lag(provider="ALPACA", dataset="price_bars", seconds=3)
    metrics.set_ingestion_backlog(queue="ingestion-low", depth=2)
    metrics.observe_ingestion_rejection(provider="SEC", error_class="SCHEMA_DRIFT")
    metrics.set_ingestion_quality(provider="ALPHA_VANTAGE", status="DEGRADED", count=1)
    metrics.set_provider_rate_limit(provider="ALPACA", remaining=199)
    metrics.observe_live_smoke(provider="ALPACA", outcome="SKIPPED_MISSING_SECRET")

    rendered = metrics.render()
    assert "platform_ingestion_job_lag_seconds" in rendered
    assert (
        'platform_ingestion_job_lag_seconds{dataset="price_bars",provider="ALPACA"} 12.0'
        in rendered
    )
    assert "platform_ingestion_cursor_lag_seconds" in rendered
    assert "platform_ingestion_rejections_total" in rendered
    assert "platform_provider_rate_limit_remaining" in rendered
    assert 'outcome="SKIPPED_MISSING_SECRET"' in rendered
