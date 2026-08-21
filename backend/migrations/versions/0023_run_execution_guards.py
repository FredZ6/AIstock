"""Make run execution observable, bounded, and point-in-time safe."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_run_execution_guards"
down_revision: str | None = "0022_single_portfolio_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "decision_snapshot",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("ALTER TABLE decision_snapshot DISABLE TRIGGER enforce_append_only")
    op.execute("UPDATE decision_snapshot SET available_at = created_at")
    op.execute("ALTER TABLE decision_snapshot ENABLE TRIGGER enforce_append_only")
    op.alter_column("decision_snapshot", "available_at", nullable=False)

    columns = (
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("last_error", postgresql.JSONB()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "research_scoring_policy_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'research-v1'"),
        ),
        sa.Column(
            "risk_policy_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'risk-v1'"),
        ),
        sa.Column(
            "execution_policy_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'execution-v1'"),
        ),
        sa.Column(
            "confidence_policy_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'confidence-v1'"),
        ),
        sa.Column(
            "prompt_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'prompt-v1'"),
        ),
        sa.Column(
            "model_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'fixture-v1'"),
        ),
    )
    for column in columns:
        op.add_column("agent_run", column)
    op.execute(
        """
        UPDATE agent_run
        SET prompt_version = CASE run_type
                WHEN 'PORTFOLIO' THEN 'portfolio-prompt-v1'
                WHEN 'ALERT_MONITOR' THEN 'deterministic-alert-v1'
                WHEN 'WEEKLY_REVIEW' THEN 'weekly-review-prompt-v1'
                ELSE 'prompt-v1'
            END,
            model_version = CASE run_type
                WHEN 'PORTFOLIO' THEN 'fixture-proposer-v1'
                WHEN 'ALERT_MONITOR' THEN 'none'
                WHEN 'WEEKLY_REVIEW' THEN 'model-v1'
                ELSE 'fixture-v1'
            END
        """
    )
    op.execute(
        """
        UPDATE risk_policy_version
        SET policy = '{
            "max_position_weight": "0.20",
            "max_gross_exposure": "1",
            "min_cash_reserve": "0.05",
            "max_daily_turnover": "0.25",
            "max_drawdown": "0.20",
            "max_research_age_days": "2",
            "earnings_blackout_days": "1"
        }'::jsonb
        WHERE version = 'risk-v1'
          AND policy = '{"source": "task_specification"}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE execution_policy_version
        SET policy = '{
            "spread_bps": "0",
            "slippage_bps": "0",
            "fee_per_share": "0",
            "minimum_fee": "0",
            "volume_participation": "1"
        }'::jsonb
        WHERE version = 'execution-v1'
          AND policy = '{"source": "task_specification"}'::jsonb
        """
    )
    op.create_check_constraint(
        op.f("ck_agent_run_attempts"),
        "agent_run",
        "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
    )
    op.execute(
        """
        CREATE FUNCTION reject_agent_run_pin_update() RETURNS trigger AS $$
        BEGIN
            IF (OLD.research_scoring_policy_version,
                OLD.risk_policy_version,
                OLD.execution_policy_version,
                OLD.confidence_policy_version,
                OLD.prompt_version,
                OLD.model_version)
               IS DISTINCT FROM
               (NEW.research_scoring_policy_version,
                NEW.risk_policy_version,
                NEW.execution_policy_version,
                NEW.confidence_policy_version,
                NEW.prompt_version,
                NEW.model_version) THEN
                RAISE EXCEPTION 'run execution pins are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER agent_run_pin_update_guard
        BEFORE UPDATE ON agent_run
        FOR EACH ROW EXECUTE FUNCTION reject_agent_run_pin_update();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER agent_run_pin_update_guard ON agent_run")
    op.execute("DROP FUNCTION reject_agent_run_pin_update()")
    op.drop_constraint(op.f("ck_agent_run_attempts"), "agent_run", type_="check")
    for name in (
        "model_version",
        "prompt_version",
        "confidence_policy_version",
        "execution_policy_version",
        "risk_policy_version",
        "research_scoring_policy_version",
        "lease_expires_at",
        "last_error",
        "max_attempts",
        "attempt_count",
    ):
        op.drop_column("agent_run", name)
    op.drop_column("decision_snapshot", "available_at")
