"""add marketevent table for CVM filings monitor

Revision ID: 0007_add_market_events
Revises: 0006_add_price_history
Create Date: 2026-11-24 23:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_market_events"
down_revision: str | None = "0006_add_price_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("document_url", sa.String(), nullable=False),
        sa.Column("ai_summary", sa.String(), nullable=True),
        sa.Column("sentiment", sa.String(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("notified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketevent_protocol", "marketevent", ["protocol"], unique=True)
    op.create_index("ix_marketevent_ticker", "marketevent", ["ticker"], unique=False)
    op.create_index("ix_marketevent_published_at", "marketevent", ["published_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_marketevent_published_at", table_name="marketevent")
    op.drop_index("ix_marketevent_ticker", table_name="marketevent")
    op.drop_index("ix_marketevent_protocol", table_name="marketevent")
    op.drop_table("marketevent")
