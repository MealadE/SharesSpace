"""Add Portfolio and PortfolioRecords models

Revision ID: 305aaee7cc81
Revises: cb4f277e7640
Create Date: 2024-08-02 00:24:30.656215

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '305aaee7cc81'
down_revision = 'cb4f277e7640'
branch_labels = None
depends_on = None


def upgrade():
    
    # Create foreign key constraints for PortfolioRecords
    with op.batch_alter_table('portfoliorecords', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_destination_pid', 'portfolio', ['destination_pid'], ['pid'], ondelete='SET NULL'
        )

    # You might need to adjust or create indexes if necessary
    # Example: batch_op.create_index('ix_some_index', ['column_name'])

def downgrade():
    # Drop foreign key constraints for PortfolioRecords
    with op.batch_alter_table('portfoliorecords', schema=None) as batch_op:
        batch_op.drop_constraint('fk_destination_pid', type_='foreignkey')
    
