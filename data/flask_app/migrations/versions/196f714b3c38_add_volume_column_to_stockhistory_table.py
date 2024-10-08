"""Add volume column to stockhistory table

Revision ID: 196f714b3c38
Revises: c98469ca6e86
Create Date: 2024-07-31 19:22:25.116751

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '196f714b3c38'
down_revision = 'c98469ca6e86'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('stockhistory', schema=None) as batch_op:
        batch_op.add_column(sa.Column('volume', sa.Numeric(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('stockhistory', schema=None) as batch_op:
        batch_op.drop_column('volume')

    # ### end Alembic commands ###
