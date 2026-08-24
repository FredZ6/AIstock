"""Add append-only Alpaca market-bar lineage and news facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_alpaca_market_news"
down_revision: str | None = "0025_ingestion_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "market_bar",
        sa.Column("normalized_record_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_market_bar_normalized_record_id_normalized_record"),
        "market_bar",
        "normalized_record",
        ["normalized_record_id"],
        ["id"],
    )
    op.add_column("market_bar", sa.Column("coverage", sa.Text(), nullable=True))
    op.add_column("market_bar", sa.Column("session", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_market_bar_coverage"),
        "market_bar",
        "coverage IS NULL OR coverage IN ('IEX', 'SIP')",
    )
    op.create_check_constraint(
        op.f("ck_market_bar_session"),
        "market_bar",
        "session IS NULL OR session IN ('PRE_MARKET', 'REGULAR', 'AFTER_HOURS', 'OVERNIGHT')",
    )
    op.execute(
        """
        UPDATE market_bar AS bar
        SET normalized_record_id = candidate.id
        FROM (
            SELECT DISTINCT ON (raw_data_object_id)
                   id, raw_data_object_id
            FROM normalized_record
            WHERE record_type IN ('market_bar', 'price_bars')
            ORDER BY raw_data_object_id, created_at, id
        ) AS candidate
        WHERE candidate.raw_data_object_id = bar.raw_data_object_id
          AND bar.normalized_record_id IS NULL
        """
    )
    op.execute(
        """
        CREATE FUNCTION require_market_bar_normalized_lineage() RETURNS trigger AS $$
        BEGIN
            IF NEW.normalized_record_id IS NULL THEN
                RAISE EXCEPTION 'market_bar requires normalized_record lineage';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER require_normalized_market_bar_lineage
        BEFORE INSERT ON market_bar
        FOR EACH ROW EXECUTE FUNCTION require_market_bar_normalized_lineage()
        """
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON market_bar
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )

    op.create_table(
        "news_article",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "raw_data_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_data_object.id"),
            nullable=False,
        ),
        sa.Column(
            "normalized_record_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("normalized_record.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("symbols", postgresql.JSONB(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pit_eligible", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "published_at <= available_at AND available_at <= ingested_at",
            name=op.f("ck_news_article_times"),
        ),
        sa.UniqueConstraint(
            "provider",
            "article_id",
            "normalized_record_id",
            name="uq_news_article_version",
        ),
    )
    op.create_index(
        "news_article_pit_idx",
        "news_article",
        ["published_at", "available_at"],
    )
    op.execute(
        """
        CREATE TRIGGER enforce_append_only
        BEFORE UPDATE OR DELETE ON news_article
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER enforce_append_only ON news_article")
    op.drop_index("news_article_pit_idx", table_name="news_article")
    op.drop_table("news_article")
    op.execute("DROP TRIGGER enforce_append_only ON market_bar")
    op.execute("DROP TRIGGER require_normalized_market_bar_lineage ON market_bar")
    op.execute("DROP FUNCTION require_market_bar_normalized_lineage()")
    op.drop_constraint(op.f("ck_market_bar_session"), "market_bar", type_="check")
    op.drop_constraint(op.f("ck_market_bar_coverage"), "market_bar", type_="check")
    op.drop_column("market_bar", "session")
    op.drop_column("market_bar", "coverage")
    op.drop_constraint(
        op.f("fk_market_bar_normalized_record_id_normalized_record"),
        "market_bar",
        type_="foreignkey",
    )
    op.drop_column("market_bar", "normalized_record_id")
