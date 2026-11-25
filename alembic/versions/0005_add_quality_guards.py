"""add quality guard columns to watchlistasset

Revision ID: 0005_add_quality_guards
Revises: 0004_add_watchlist
Create Date: 2026-11-24 22:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_quality_guards"
down_revision: str | None = "0004_add_watchlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("watchlistasset", sa.Column("profit_margin", sa.Float(), nullable=True))
    op.add_column("watchlistasset", sa.Column("debt_to_equity", sa.Float(), nullable=True))
    op.add_column("watchlistasset", sa.Column("drawdown_52w", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlistasset", "drawdown_52w")
    op.drop_column("watchlistasset", "debt_to_equity")
    op.drop_column("watchlistasset", "profit_margin")
