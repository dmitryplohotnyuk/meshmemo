"""Initial archive; keep this migration independent of future models."""

from alembic import op
import sqlalchemy as sa

revision = "0001_history"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("archive", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("device", sa.String, nullable=True),
                    sa.Column("scope_secret", sa.LargeBinary, nullable=False))
    op.create_table(
        "messages",
        sa.Column("row_id", sa.Integer, primary_key=True),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("sender", sa.BigInteger, nullable=False),
        sa.Column("packet_id", sa.BigInteger, nullable=False),
        sa.Column("channel_index", sa.Integer, nullable=False),
        sa.Column("payload", sa.LargeBinary, nullable=False),
        sa.Column("decoded_data", sa.LargeBinary, nullable=False),
        sa.Column("raw_envelope", sa.LargeBinary, nullable=False),
        sa.Column("received_at", sa.BigInteger, nullable=False),
        sa.Column("last_seen_at", sa.BigInteger, nullable=False),
        sa.Column("rx_time", sa.BigInteger, nullable=False),
        sa.Column("time_quality", sa.String, nullable=False),
        sa.Column("reply_id", sa.BigInteger, nullable=False),
        sa.Column("emoji", sa.BigInteger, nullable=False),
        sa.Column("seen_count", sa.Integer, nullable=False),
        sa.Column("collision", sa.Boolean, nullable=False),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_message_identity", "messages", ["scope", "sender", "packet_id", "received_at"])
    op.create_index("ix_message_history", "messages", ["scope", "received_at", "row_id"])
    op.create_index("ix_message_retention", "messages", ["received_at"])


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported; restore a backup instead")
