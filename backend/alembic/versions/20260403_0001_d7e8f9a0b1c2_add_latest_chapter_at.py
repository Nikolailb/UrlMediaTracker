"""add_latest_chapter_at_to_tracked_items

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-04-03 00:01:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.add_column(
            sa.Column("latest_chapter_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.drop_column("latest_chapter_at")
