"""Server-side channel keys and a disabled-by-default remote administration policy."""
from alembic import op
import sqlalchemy as sa
revision = '0005_catalog'
down_revision = '0004_controls'
branch_labels = depends_on = None

def upgrade():
    op.create_table('channel_catalog',
        sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('name',sa.String,nullable=False),
        sa.Column('key_ciphertext',sa.LargeBinary,nullable=False),
        sa.Column('identity',sa.String,nullable=False,unique=True),
        sa.Column('capture',sa.Boolean,nullable=False),
        sa.Column('replay',sa.Boolean,nullable=False),
        sa.Column('last_seen',sa.BigInteger,nullable=True),
        sqlite_autoincrement=True)
    op.create_table('channel_admin_policy',sa.Column('id',sa.Integer,primary_key=True),
        sa.Column('enabled',sa.Boolean,nullable=False),sa.Column('public_keys',sa.Text,nullable=False))
    op.execute("INSERT INTO channel_admin_policy VALUES(1,0,'[]')")
    op.create_table('channel_admin_requests',sa.Column('identity',sa.String,primary_key=True),
        sa.Column('received_at',sa.BigInteger,nullable=False))

def downgrade():
    raise RuntimeError('Restore a backup instead of destructive downgrade')
