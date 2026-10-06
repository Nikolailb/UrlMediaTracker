"""Store verified ToC links and optional extraction guidance (REQ-016)."""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0004"
down_revision = "20261005_0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tracked_items") as batch:
        batch.add_column(sa.Column("latest_chapter_url", sa.String(2000)))
        batch.add_column(sa.Column("first_chapter_url", sa.String(2000)))
        batch.add_column(sa.Column("preferred_group", sa.String(200)))
        batch.add_column(sa.Column("toc_examples_json", sa.String(5000)))
        batch.add_column(sa.Column("toc_row_class", sa.String(200)))
        batch.add_column(sa.Column("toc_latest_page_url", sa.String(2000)))


def downgrade():
    with op.batch_alter_table("tracked_items") as batch:
        batch.drop_column("toc_latest_page_url")
        batch.drop_column("toc_row_class")
        batch.drop_column("toc_examples_json")
        batch.drop_column("preferred_group")
        batch.drop_column("latest_chapter_url")
        batch.drop_column("first_chapter_url")
