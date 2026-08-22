# PostgreSQL backup and restore

## RPO

The backup interval is the maximum loss window; target 24 hours in fixture/paper environments.

## RTO

Target 60 minutes for a validated fixture/paper restore.

```bash
docker compose exec -T postgres pg_dump -U postgres -d stock_platform -Fc > stock-platform.dump
docker compose exec -T postgres createdb -U postgres stock_platform_restore_check
docker compose exec -T postgres psql -U postgres -d stock_platform_restore_check -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT timescaledb_pre_restore();"
docker compose exec -T postgres pg_restore -U postgres -d stock_platform_restore_check --no-owner < stock-platform.dump
docker compose exec -T postgres psql -U postgres -d stock_platform_restore_check -v ON_ERROR_STOP=1 -c "SELECT timescaledb_post_restore();"
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform_restore_check uv run alembic -c backend/alembic.ini upgrade head
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:55432/stock_platform_restore_check uv run pytest backend/tests/integration/db -q
docker compose exec -T postgres dropdb -U postgres stock_platform_restore_check
```

Restore separately first. Validate migrations, append-only triggers, lineage, and row counts.
