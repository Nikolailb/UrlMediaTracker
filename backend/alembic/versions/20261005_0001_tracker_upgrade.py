"""Add checker, account, and library fields without deleting legacy data."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0001"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        b.alter_column("email", existing_type=sa.String(255), nullable=True)
    with op.batch_alter_table("tracked_items") as b:
        b.add_column(sa.Column("series_url", sa.String(2000)))
        b.add_column(sa.Column("strategy_override", sa.String(50)))
        b.add_column(sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("note", sa.String(2000)))
        b.add_column(sa.Column("cover_filename", sa.String(100)))
        b.add_column(sa.Column("pending_latest_chapter", sa.String(50)))
        b.add_column(sa.Column("pending_chapter_url", sa.String(2000)))
        b.add_column(sa.Column("dismissed_candidate", sa.String(50)))
        b.add_column(sa.Column("last_outcome", sa.String(30)))
        b.create_index("ix_items_owner_sensitive", ["user_id", "is_sensitive"])
    with op.batch_alter_table("chapter_check_logs") as b:
        b.add_column(sa.Column("outcome", sa.String(30)))
        b.add_column(sa.Column("pending_chapter", sa.String(50)))
    op.create_table("invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)))
    op.create_table("login_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("safe_view_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_table("login_sessions")
    op.drop_table("invites")
    with op.batch_alter_table("chapter_check_logs") as b:
        b.drop_column("pending_chapter")
        b.drop_column("outcome")
    with op.batch_alter_table("tracked_items") as b:
        b.drop_index("ix_items_owner_sensitive")
        for name in ("last_outcome", "dismissed_candidate", "pending_chapter_url", "pending_latest_chapter", "cover_filename", "note", "is_sensitive", "strategy_override", "series_url"):
            b.drop_column(name)
    with op.batch_alter_table("users") as b:
        b.drop_column("is_active")
        b.drop_column("is_admin")
        b.alter_column("email", existing_type=sa.String(255), nullable=False)
