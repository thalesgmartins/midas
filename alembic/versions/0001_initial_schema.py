"""create initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-24 00:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assetclass",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("target_pct", sa.Float(), nullable=False),
        sa.Column("band_pp", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assetclass_name", "assetclass", ["name"], unique=True)

    op.create_table(
        "asset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("asset_class_id", sa.Integer(), nullable=False),
        sa.Column("segment", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("divisible", sa.Boolean(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("price_ceiling", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(), nullable=False),
        sa.Column("price_updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_class_id"], ["assetclass.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_ticker", "asset", ["ticker"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_asset_ticker", table_name="asset")
    op.drop_table("asset")
    op.drop_index("ix_assetclass_name", table_name="assetclass")
    op.drop_table("assetclass")
