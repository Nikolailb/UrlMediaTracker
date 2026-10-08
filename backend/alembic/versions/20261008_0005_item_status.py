"""Add item lifecycle and saved status filters (REQ-022)."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0005"
down_revision = "20261006_0004"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tracked_items") as batch:
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="ONGOING"))
    op.execute("UPDATE tracked_items SET status = CASE WHEN is_active = 1 THEN 'ONGOING' ELSE 'PAUSED' END")
    with op.batch_alter_table("filter_presets") as batch:
        batch.add_column(sa.Column("statuses_json", sa.Text(), nullable=False, server_default='["ONGOING","COMPLETED"]'))
    op.execute("UPDATE filter_presets SET statuses_json = CASE WHEN include_inactive = 1 THEN '[\"ONGOING\",\"PAUSED\",\"COMPLETED\",\"FINISHED\"]' ELSE '[\"ONGOING\",\"COMPLETED\"]' END")


def downgrade():
    with op.batch_alter_table("filter_presets") as batch:
        batch.drop_column("statuses_json")
    with op.batch_alter_table("tracked_items") as batch:
        batch.drop_column("status")
