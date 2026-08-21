"""Add durable API run admission and watchlist state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_api_control_plane"
down_revision: str | None = "0019_controlled_learning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alert_event", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.add_column("alert_event", sa.Column("acknowledged_by", sa.Text()))
    op.create_table(
        "agent_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_type", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False),
        sa.Column("symbol", sa.Text()),
        sa.Column("decision_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'QUEUED'")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("idempotency_key", name="agent_run_idempotency_key_key"),
        sa.CheckConstraint(
            "run_type IN ('RESEARCH', 'PORTFOLIO', 'ALERT_MONITOR', 'WEEKLY_REVIEW')",
            name=op.f("ck_agent_run_type"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name=op.f("ck_agent_run_status"),
        ),
        sa.CheckConstraint("data_cutoff <= decision_time", name=op.f("ck_agent_run_cutoff")),
    )
    op.create_index(
        "agent_run_active_created_idx", "agent_run", ["status", "created_at"], unique=False
    )
    op.create_table(
        "watchlist_item",
        sa.Column("symbol", sa.Text(), primary_key=True),
        sa.Column("daily_research", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "intraday_monitoring", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "thresholds",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("watchlist_item")
    op.drop_index("agent_run_active_created_idx", table_name="agent_run")
    op.drop_table("agent_run")
    op.drop_column("alert_event", "acknowledged_by")
    op.drop_column("alert_event", "acknowledged_at")
