"""add pricepoint table for historical risk analytics

Revision ID: 0006_add_price_history
Revises: 0005_add_quality_guards
Create Date: 2026-11-24 22:52:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_price_history"
down_revision: str | None = "0005_add_quality_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pricepoint",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("ref_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "ref_date", name="uq_pricepoint_ticker_date"),
    )
    op.create_index("ix_pricepoint_ticker", "pricepoint", ["ticker"], unique=False)
    op.create_index("ix_pricepoint_ref_date", "pricepoint", ["ref_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pricepoint_ref_date", table_name="pricepoint")
    op.drop_index("ix_pricepoint_ticker", table_name="pricepoint")
    op.drop_table("pricepoint")
