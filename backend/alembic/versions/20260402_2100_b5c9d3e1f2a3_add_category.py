"""add_category_to_tracked_items

Adds a nullable category column (plain String) to tracked_items.

Revision ID: b5c9d3e1f2a3
Revises: a3f81c2e9b04
Create Date: 2026-04-02 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c9d3e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a3f81c2e9b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.drop_column("category")
