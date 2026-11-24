"""add band_mode to assetclass

Revision ID: 0002_add_band_mode
Revises: 0001_initial_schema
Create Date: 2026-11-24 01:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_band_mode"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assetclass",
        sa.Column("band_mode", sa.String(), nullable=False, server_default="pp"),
    )


def downgrade() -> None:
    op.drop_column("assetclass", "band_mode")
