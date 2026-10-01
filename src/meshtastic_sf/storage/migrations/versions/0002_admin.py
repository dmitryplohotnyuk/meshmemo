"""Persist admin settings and display metadata, never channel keys."""

from alembic import op
import sqlalchemy as sa

revision = "0002_admin"
down_revision = "0001_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("server_settings", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("max_records", sa.Integer, nullable=False),
                    sa.Column("dedupe_seconds", sa.Integer, nullable=False),
                    sa.Column("retention_days", sa.Integer, nullable=False),
                    sa.Column("capture_enabled", sa.Boolean, nullable=False))
    op.execute("INSERT INTO server_settings VALUES (1, 100000, 86400, 0, 1)")
    op.create_table("channel_labels", sa.Column("scope", sa.String(64), primary_key=True),
                    sa.Column("name", sa.String, nullable=False),
                    sa.Column("channel_index", sa.Integer, nullable=False))
    op.create_table("node_labels", sa.Column("node_num", sa.BigInteger, primary_key=True),
                    sa.Column("name", sa.String, nullable=False))


def downgrade():
    raise RuntimeError("Restore a backup instead of destructive downgrade")
