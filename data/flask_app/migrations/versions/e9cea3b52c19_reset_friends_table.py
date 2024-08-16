from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection

# revision identifiers, used by Alembic.
revision = 'e9cea3b52c19'
down_revision = '4de74f200a89'  # Adjust this as needed
branch_labels = None
depends_on = None

def upgrade():
    # Drop the table if it exists
    conn = op.get_bind()
    inspector = reflection.Inspector.from_engine(conn)
    if 'friends' in inspector.get_table_names():
        op.drop_table('friends')
    
    # Recreate the table
    op.create_table(
        'friends',
        sa.Column('user_id1', sa.String(length=64), nullable=False),
        sa.Column('user_id2', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('timestamp', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('user_id1', 'user_id2'),
        sa.UniqueConstraint('user_id1', 'user_id2', name='unique_friendship')
    )

def downgrade():
    # Drop the table if it exists
    conn = op.get_bind()
    inspector = reflection.Inspector.from_engine(conn)
    if 'friends' in inspector.get_table_names():
        op.drop_table('friends')
