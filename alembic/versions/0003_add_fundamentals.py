"""add assetfundamentals table

Revision ID: 0003_add_fundamentals
Revises: 0002_add_band_mode
Create Date: 2026-11-24 02:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_fundamentals"
down_revision: str | None = "0002_add_band_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assetfundamentals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("lpa", sa.Float(), nullable=True),
        sa.Column("vpa", sa.Float(), nullable=True),
        sa.Column("pl", sa.Float(), nullable=True),
        sa.Column("pvp", sa.Float(), nullable=True),
        sa.Column("roe", sa.Float(), nullable=True),
        sa.Column("payout", sa.Float(), nullable=True),
        sa.Column("div_12m", sa.Float(), nullable=True),
        sa.Column("div_avg_5y", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assetfundamentals_asset_id", "assetfundamentals", ["asset_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_assetfundamentals_asset_id", table_name="assetfundamentals")
    op.drop_table("assetfundamentals")
