"""Enable TimescaleDB and convert time-series tables to hypertables."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_timescale_hypertables"
down_revision: str | None = "0001_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    for table_name in ("market_bar", "option_snapshot", "portfolio_nav", "alert_metric"):
        op.execute(f"SELECT create_hypertable('{table_name}', 'event_time', if_not_exists => TRUE)")


def downgrade() -> None:
    # TimescaleDB hypertables retain ordinary table semantics; Task 3 supports forward rebuilds.
    pass
