"""Attach newly observed evidence gaps to their owning research run."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_evidence_gap_run_lineage"
down_revision: str | None = "0036_runtime_acceptance_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_gap", sa.Column("run_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "evidence_gap_run_id_fkey",
        "evidence_gap",
        "agent_run",
        ["run_id"],
        ["id"],
    )
    op.create_index("ix_evidence_gap_run_id", "evidence_gap", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_gap_run_id", table_name="evidence_gap")
    op.drop_constraint("evidence_gap_run_id_fkey", "evidence_gap", type_="foreignkey")
    op.drop_column("evidence_gap", "run_id")
