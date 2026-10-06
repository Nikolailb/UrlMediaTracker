"""Save the Filters menu sort choice in each preset (REQ-009)."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0003"
down_revision = "20261005_0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("filter_presets") as batch:
        batch.add_column(sa.Column("sort_key", sa.String(30), nullable=False, server_default="latest_chapter_at"))
        batch.add_column(sa.Column("sort_dir", sa.String(4), nullable=False, server_default="desc"))


def downgrade():
    with op.batch_alter_table("filter_presets") as batch:
        batch.drop_column("sort_dir")
        batch.drop_column("sort_key")
