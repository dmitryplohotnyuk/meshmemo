"""Replay is opt-in; reserve transport identities before any USB submission."""
from alembic import op
import sqlalchemy as sa

revision = "0003_replay"
down_revision = "0002_admin"
branch_labels = depends_on = None


def upgrade():
    op.add_column("server_settings", sa.Column("replay_enabled", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_table("replay_ids", sa.Column("sender", sa.BigInteger, primary_key=True),
                    sa.Column("packet_id", sa.BigInteger, primary_key=True))


def downgrade():
    raise RuntimeError("Restore a backup instead of destructive downgrade")
