"""Normalize evaluation constraint names without rewriting persisted evidence."""

from collections.abc import Sequence

from alembic import op

revision: str = "0039_eval_constraint_names"
down_revision: str | None = "0038_evaluation_read_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENAMES = (
    ("eval_run", "ck_eval_run_ck_eval_run_status", "ck_eval_run_status"),
    ("eval_run", "ck_eval_run_ck_eval_run_mode", "ck_eval_run_mode"),
    ("eval_run", "ck_eval_run_ck_eval_run_case_count", "ck_eval_run_case_count"),
    ("eval_run", "ck_eval_run_ck_eval_run_status_passed", "ck_eval_run_status_passed"),
    ("eval_run", "ck_eval_run_ck_eval_run_summary_hash", "ck_eval_run_summary_hash"),
    (
        "regression_gate_result",
        "ck_regression_gate_result_ck_regression_gate_comparison",
        "ck_regression_gate_comparison",
    ),
)


def upgrade() -> None:
    for table_name, old_name, new_name in _RENAMES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{old_name}'
                ) THEN
                    ALTER TABLE {table_name} RENAME CONSTRAINT {old_name} TO {new_name};
                END IF;
            END $$
            """
        )


def downgrade() -> None:
    # Constraint names are normalized metadata, not a reversible data change.
    pass
