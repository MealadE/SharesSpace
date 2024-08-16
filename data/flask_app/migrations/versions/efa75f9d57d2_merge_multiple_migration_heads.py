"""Merge multiple migration heads

Revision ID: efa75f9d57d2
Revises: 45600df0d15c, 7e0b3f757c0e, 86d3f70320b4, f1841cc041f5
Create Date: 2024-08-02 00:05:55.910931

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'efa75f9d57d2'
down_revision = ('45600df0d15c', '7e0b3f757c0e', '86d3f70320b4', 'f1841cc041f5')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
