# PostgreSQL backup and restore

## RPO

The backup interval is the maximum loss window; target 24 hours in fixture/paper environments.

## RTO

Target 60 minutes for a validated fixture/paper restore.

```bash
docker compose exec -T postgres pg_dump -U postgres -d stock_platform -Fc > stock-platform.dump
createdb stock_platform_restore_check
pg_restore --clean --if-exists --no-owner -d stock_platform_restore_check stock-platform.dump
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform_restore_check uv run alembic -c backend/alembic.ini upgrade head
```

Restore separately first. Validate migrations, append-only triggers, lineage, and row counts.
