"""Require every append-only financial fact to reference its SEC filing."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_financial_filing_fk"
down_revision: str | None = "0030_financial_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("financial_fact", "sec_filing_id", existing_type=sa.UUID(), nullable=False)


def downgrade() -> None:
    op.alter_column("financial_fact", "sec_filing_id", existing_type=sa.UUID(), nullable=True)
