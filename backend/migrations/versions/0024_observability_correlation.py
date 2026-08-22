"""Persist one bounded correlation path for runs, events, tools, and alerts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_observability_correlation"
down_revision: str | None = "0023_run_execution_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("agent_run", "agent_event", "tool_call", "alert_event"):
        op.add_column(
            table,
            sa.Column(
                "correlation_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
        )
    op.create_index("agent_run_correlation_idx", "agent_run", ["correlation_id"])
    op.create_index("agent_event_correlation_idx", "agent_event", ["correlation_id"])
    op.create_index("tool_call_correlation_idx", "tool_call", ["correlation_id"])
    op.create_index("alert_event_correlation_idx", "alert_event", ["correlation_id"])


def downgrade() -> None:
    for table in ("alert_event", "tool_call", "agent_event", "agent_run"):
        op.drop_index(f"{table}_correlation_idx", table_name=table)
        op.drop_column(table, "correlation_id")
