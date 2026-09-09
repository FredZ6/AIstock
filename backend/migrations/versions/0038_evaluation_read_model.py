"""Add append-only persisted evaluation runs, metrics, and release gates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038_evaluation_read_model"
down_revision: str | None = "0037_evidence_gap_run_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_run",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("research_scoring_policy_version", sa.Text(), nullable=False),
        sa.Column("risk_policy_version", sa.Text(), nullable=False),
        sa.Column("execution_policy_version", sa.Text(), nullable=False),
        sa.Column("confidence_policy_version", sa.Text(), nullable=False),
        sa.Column("gate_policy_version", sa.Text(), nullable=False),
        sa.Column("summary_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('PASSED', 'FAILED')", name=op.f("ck_eval_run_status")),
        sa.CheckConstraint("mode = 'fixture'", name=op.f("ck_eval_run_mode")),
        sa.CheckConstraint("case_count > 0", name=op.f("ck_eval_run_case_count")),
        sa.CheckConstraint("(status = 'PASSED') = passed", name=op.f("ck_eval_run_status_passed")),
        sa.CheckConstraint(
            "summary_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_eval_run_summary_hash")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "eval_run_created_idx", "eval_run", [sa.text("created_at DESC"), sa.text("id DESC")]
    )
    op.create_table(
        "eval_metric",
        sa.Column("eval_run_id", sa.UUID(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("metric_value", sa.Numeric(), nullable=False),
        sa.Column("case_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("case_hashes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_run.id"]),
        sa.PrimaryKeyConstraint("eval_run_id", "metric_name"),
    )
    op.create_table(
        "regression_gate_result",
        sa.Column("eval_run_id", sa.UUID(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column("comparison", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Numeric(), nullable=False),
        sa.Column("observed", sa.Numeric()),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "comparison IN ('AT_LEAST', 'AT_MOST', 'LESS_THAN')",
            name=op.f("ck_regression_gate_comparison"),
        ),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_run.id"]),
        sa.PrimaryKeyConstraint("eval_run_id", "metric_name"),
    )
    for table_name in ("eval_run", "eval_metric", "regression_gate_result"):
        op.execute(
            f"""
            CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
            """
        )


def downgrade() -> None:
    for table_name in ("regression_gate_result", "eval_metric", "eval_run"):
        op.execute(f"DROP TRIGGER enforce_append_only ON {table_name}")
    op.drop_table("regression_gate_result")
    op.drop_table("eval_metric")
    op.drop_index("eval_run_created_idx", table_name="eval_run")
    op.drop_table("eval_run")
