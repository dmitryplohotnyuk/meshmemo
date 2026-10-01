"""Replay policy and persistent USB selection."""
from alembic import op
import sqlalchemy as sa

revision = '0004_controls'
down_revision = '0003_replay'
branch_labels = depends_on = None

def upgrade():
    for name, value in [('replay_limit',20),('replay_window_minutes',1440),('replay_max_window_minutes',10080),
                        ('replay_interval_seconds',5),('replay_cooldown_seconds',60),('replay_heartbeat_seconds',900)]:
        op.add_column('server_settings',sa.Column(name,sa.Integer,nullable=False,server_default=str(value)))
    op.add_column('server_settings',sa.Column('replay_heartbeat_enabled',sa.Boolean,nullable=False,server_default=sa.true()))
    op.create_table('connection_settings',sa.Column('id',sa.Integer,primary_key=True),
                    sa.Column('mode',sa.String,nullable=False),sa.Column('port',sa.String,nullable=False),
                    sa.Column('identity',sa.String,nullable=False),sa.Column('configured',sa.Boolean,nullable=False))
    op.execute("INSERT INTO connection_settings VALUES(1,'off','','',0)")

def downgrade():
    raise RuntimeError('Restore a backup instead of destructive downgrade')
