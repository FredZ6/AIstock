# Stuck run or lost worker

## RPO

Zero loss of committed AgentEvent, decisions, fills, or ledger entries.

## RTO

One recovery interval (60 seconds) plus normal task duration.

```bash
docker compose exec postgres psql -U postgres -d stock_platform -c "select id,status,attempt_count,lease_expires_at from agent_run where status in ('QUEUED','RUNNING');"
uv run python -c "from stock_platform.workers.schedules import recover_queued; recover_queued()"
```

Only expired, non-exhausted runs are requeued. Database idempotency prevents duplicate effects.
