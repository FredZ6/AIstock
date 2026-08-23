# Redis loss

## RPO

Zero authoritative database fact loss. Uncommitted stream messages may require provider replay.

## RTO

Five minutes for restart and worker resubscription.

```bash
./scripts/verify-recovery.sh
```

The script restores a separate TimescaleDB copy, dispatches a real research run, and persists one
deterministically identified paper fill with its balanced ledger. It then restarts Redis and the
worker, replays both probes, and verifies the scoped AgentEvent, ToolCall, PaperFill, and CashLedger
counts do not change. Recover queued runs from PostgreSQL. Never reconstruct PaperFill or CashLedger
from Redis.
