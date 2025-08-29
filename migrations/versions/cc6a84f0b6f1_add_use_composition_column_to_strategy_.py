"""Add use_composition column to strategy_configurations

Revision ID: cc6a84f0b6f1
Revises: 
Create Date: 2025-08-29 19:19:42.501080

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cc6a84f0b6f1'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add use_composition column to strategy_configurations table
    op.add_column('strategy_configurations', sa.Column('use_composition', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    
    # Create index for performance
    op.create_index('idx_strategy_configurations_composition', 'strategy_configurations', ['use_composition'])
    
    # Update existing records to use composition by default
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE strategy_configurations 
        SET use_composition = TRUE 
        WHERE strategy_type IN ('MomentumProcessor', 'MeanReversionProcessor')
    """))
    
    connection.execute(sa.text("""
        UPDATE strategy_configurations 
        SET use_composition = FALSE 
        WHERE strategy_type IN ('SimpleMomentumStrategy', 'MomentumStrategy', 'MeanReversionStrategy')
    """))


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_strategy_configurations_composition', 'strategy_configurations')
    
    # Drop column
    op.drop_column('strategy_configurations', 'use_composition')