"""toc_scraper_strategy

Adds toc_url column to tracked_items and converts the check_strategy column
from a SQLAlchemy Enum type to a plain String(50).  Using a String column means
new strategy keys can be registered in Python without requiring a DB migration.

Revision ID: a3f81c2e9b04
Revises: df12640c1aa2
Create Date: 2026-04-02 19:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f81c2e9b04"
down_revision: Union[str, Sequence[str], None] = "df12640c1aa2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite does not support ALTER COLUMN in-place; batch mode recreates the
    # table transparently while preserving all existing rows.
    with op.batch_alter_table("tracked_items") as batch_op:
        # Change check_strategy from an Enum constraint to a plain string.
        # Existing "INCREMENTAL_PROBE" values are preserved as-is.
        batch_op.alter_column(
            "check_strategy",
            type_=sa.String(50),
            existing_nullable=False,
        )
        # Add the optional table-of-contents URL for ToCScraperStrategy.
        batch_op.add_column(sa.Column("toc_url", sa.String(2000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tracked_items") as batch_op:
        batch_op.drop_column("toc_url")
        batch_op.alter_column(
            "check_strategy",
            type_=sa.Enum("INCREMENTAL_PROBE", name="checkstrategy"),
            existing_nullable=False,
        )
