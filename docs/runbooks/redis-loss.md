# Redis loss

## RPO

Zero authoritative database fact loss. Uncommitted stream messages may require provider replay.

## RTO

Five minutes for restart and worker resubscription.

```bash
./scripts/verify-recovery.sh
```

The script restores a separate TimescaleDB copy, snapshots AgentEvent and PaperFill counts, starts a
real Celery worker, restarts Redis, restarts the worker under a fresh node name, compares the durable
counts, and runs the replay/idempotency regressions. Recover queued runs from PostgreSQL. Never
reconstruct PaperFill or CashLedger from Redis.
