# Provider outage

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
