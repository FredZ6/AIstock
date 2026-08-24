"""Enforce point-in-time eligibility for append-only news facts."""

from collections.abc import Sequence

from alembic import op

revision: str = "0027_alpaca_news_pit_guard"
down_revision: str | None = "0026_alpaca_market_news"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_news_article_pit_eligibility"),
        "news_article",
        "(observed_at IS NULL OR "
        "(published_at <= observed_at AND observed_at <= available_at)) "
        "AND (NOT pit_eligible OR observed_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_news_article_pit_eligibility"),
        "news_article",
        type_="check",
    )
