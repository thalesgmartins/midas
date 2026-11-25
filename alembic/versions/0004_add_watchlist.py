"""add watchlistasset table for screener

Revision ID: 0004_add_watchlist
Revises: 0003_add_fundamentals
Create Date: 2026-11-24 20:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_watchlist"
down_revision: str | None = "0003_add_fundamentals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlistasset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("class_name", sa.String(), nullable=False),
        sa.Column("segment", sa.String(), nullable=False),
        sa.Column("is_perennial", sa.Boolean(), nullable=False),
        sa.Column("in_watchlist", sa.Boolean(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("lpa", sa.Float(), nullable=True),
        sa.Column("vpa", sa.Float(), nullable=True),
        sa.Column("pl", sa.Float(), nullable=True),
        sa.Column("pvp", sa.Float(), nullable=True),
        sa.Column("roe", sa.Float(), nullable=True),
        sa.Column("payout", sa.Float(), nullable=True),
        sa.Column("div_12m", sa.Float(), nullable=True),
        sa.Column("div_avg_5y", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watchlistasset_ticker", "watchlistasset", ["ticker"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_watchlistasset_ticker", table_name="watchlistasset")
    op.drop_table("watchlistasset")
