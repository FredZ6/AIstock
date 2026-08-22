# Redis loss

## RPO

Zero authoritative database fact loss. Uncommitted stream messages may require provider replay.

## RTO

Five minutes for restart and worker resubscription.

```bash
docker compose restart redis
docker compose exec redis redis-cli ping
uv run pytest backend/tests/integration/recovery -q
docker compose exec postgres psql -U postgres -d stock_platform -c "select count(*) from agent_event; select count(*) from paper_fill;"
```

Recover queued runs from PostgreSQL. Never reconstruct PaperFill or CashLedger from Redis.
