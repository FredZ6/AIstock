"""Allow at most one append-only reversal for each paper fill."""

from collections.abc import Sequence

from alembic import op

revision: str = "0011_unique_paper_fill_reversal"
down_revision: str | None = "0010_paper_order_intent_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX paper_fill_one_reversal_per_fill_idx
        ON paper_fill (reversal_of_id)
        WHERE reversal_of_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS paper_fill_one_reversal_per_fill_idx")
