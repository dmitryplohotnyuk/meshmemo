"""SQLAlchemy Core schema; versioned DDL lives in migrations."""

import sqlalchemy as sa

metadata = sa.MetaData()
settings = sa.Table("server_settings", metadata,
                    sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("max_records", sa.Integer, nullable=False),
                    sa.Column("dedupe_seconds", sa.Integer, nullable=False),
                    sa.Column("retention_days", sa.Integer, nullable=False),
                    sa.Column("capture_enabled", sa.Boolean, nullable=False),
                    sa.Column("replay_enabled", sa.Boolean, nullable=False),
                    sa.Column("replay_limit", sa.Integer, nullable=False),
                    sa.Column("replay_window_minutes", sa.Integer, nullable=False),
                    sa.Column("replay_max_window_minutes", sa.Integer, nullable=False),
                    sa.Column("replay_interval_seconds", sa.Integer, nullable=False),
                    sa.Column("replay_cooldown_seconds", sa.Integer, nullable=False),
                    sa.Column("replay_heartbeat_seconds", sa.Integer, nullable=False),
                    sa.Column("replay_heartbeat_enabled", sa.Boolean, nullable=False))
connection_settings = sa.Table('connection_settings',metadata,
                    sa.Column('id',sa.Integer,primary_key=True),sa.Column('mode',sa.String,nullable=False),
                    sa.Column('port',sa.String,nullable=False),sa.Column('identity',sa.String,nullable=False),
                    sa.Column('configured',sa.Boolean,nullable=False))
replay_ids = sa.Table("replay_ids", metadata,
                      sa.Column("sender", sa.BigInteger, primary_key=True),
                      sa.Column("packet_id", sa.BigInteger, primary_key=True))
channels = sa.Table("channel_labels", metadata,
                    sa.Column("scope", sa.String(64), primary_key=True),
                    sa.Column("name", sa.String, nullable=False),
                    sa.Column("channel_index", sa.Integer, nullable=False))
nodes = sa.Table("node_labels", metadata,
                 sa.Column("node_num", sa.BigInteger, primary_key=True),
                 sa.Column("name", sa.String, nullable=False))
archive = sa.Table(
    "archive", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("device", sa.String, nullable=True),
    sa.Column("scope_secret", sa.LargeBinary, nullable=False),
)
messages = sa.Table(
    "messages", metadata,
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
sa.Index("ix_message_identity", messages.c.scope, messages.c.sender, messages.c.packet_id, messages.c.received_at)
sa.Index("ix_message_history", messages.c.scope, messages.c.received_at, messages.c.row_id)
sa.Index("ix_message_retention", messages.c.received_at)

catalog = sa.Table('channel_catalog', metadata,
    sa.Column('id',sa.Integer,primary_key=True),sa.Column('name',sa.String,nullable=False),
    sa.Column('key_ciphertext',sa.LargeBinary,nullable=False),sa.Column('identity',sa.String,nullable=False),
    sa.Column('capture',sa.Boolean,nullable=False),sa.Column('replay',sa.Boolean,nullable=False),
    sa.Column('last_seen',sa.BigInteger))
admin_policy = sa.Table('channel_admin_policy',metadata,sa.Column('id',sa.Integer,primary_key=True),
    sa.Column('enabled',sa.Boolean,nullable=False),sa.Column('public_keys',sa.Text,nullable=False))
admin_requests = sa.Table('channel_admin_requests',metadata,sa.Column('identity',sa.String,primary_key=True),
    sa.Column('received_at',sa.BigInteger,nullable=False))
