"""Pin the normalization algorithm on every normalized record."""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_normalization_version"
down_revision: str | None = "0003_market_data_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE normalized_record
            ADD COLUMN normalization_version text NOT NULL DEFAULT 'legacy-v0',
            ADD CONSTRAINT uq_normalized_record_version
                UNIQUE (raw_data_object_id, record_type, normalization_version);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE normalized_record
            DROP CONSTRAINT uq_normalized_record_version,
            DROP COLUMN normalization_version;
        """
    )
