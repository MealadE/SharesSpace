"""remake friends again

Revision ID: eec368cd1c75
Revises: 84dba3441579
Create Date: 2024-08-02 01:53:15.107677

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eec368cd1c75'
down_revision = '84dba3441579'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the friends table
    op.drop_table('friends')


def downgrade():
    # Recreate the friends table
    op.create_table(
        'friends',
        sa.Column('user_id1', sa.String(length=64), nullable=False),
        sa.Column('user_id2', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id1'], ['users.username'], ),
        sa.ForeignKeyConstraint(['user_id2'], ['users.username'], ),
        sa.PrimaryKeyConstraint('user_id1', 'user_id2'),
        sa.UniqueConstraint('user_id1', 'user_id2', name='unique_friendship')
    )