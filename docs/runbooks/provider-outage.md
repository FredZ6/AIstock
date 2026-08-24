# Provider outage

## Managed Alpaca data stream

Run `make alpaca-stream` under the deployment process supervisor with restart-on-failure enabled.
The process connects only to `wss://stream.data.alpaca.markets/v2/{iex|sip}` and requires explicit
data credentials plus a persisted entitlement configuration. Each wire batch is archived in MinIO
before its Celery persistence task is published; a failed publish does not advance the reconnect
watermark. A recovery sidecar preserves the first receipt time. On every supervised restart, a
low-priority reconciler checks PostgreSQL and republishes only unreferenced objects in bounded
100-object pages with a continuation cursor. Monitor the process exit/restart counter together with
Celery queue depth and MinIO health.

## RPO

Zero loss of ingested raw objects. New provider observations may be absent.

## RTO

Fixture/degraded reads within 5 minutes.

```bash
curl -fsS http://localhost:8000/api/v1/providers/health
curl -fsS http://localhost:8000/metrics | rg platform_provider_calls
docker compose logs --since=15m otel-collector
```

Keep the circuit open, expose `UNAVAILABLE`, preserve cutoff-safe facts, and never invent data.
