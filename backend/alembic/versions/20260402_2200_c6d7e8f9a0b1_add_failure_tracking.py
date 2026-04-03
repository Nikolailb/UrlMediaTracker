"""add_failure_tracking_to_tracked_items

Revision ID: c6d7e8f9a0b1
Revises: b5c9d3e1f2a3
Create Date: 2026-04-02 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "c6d7e8f9a0b1"
down_revision = "b5c9d3e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.add_column(
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("last_error", sa.String(1000), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.drop_column("last_error")
        batch_op.drop_column("consecutive_failures")
