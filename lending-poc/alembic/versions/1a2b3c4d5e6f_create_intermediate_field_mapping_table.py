"""create intermediate_field_mapping table

Revision ID: 1a2b3c4d5e6f
Revises: 
Create Date: 2026-08-11 15:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'intermediate_field_mapping',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('field_mapper_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('processing_date', sa.DateTime(), nullable=True),
        sa.Column('validated', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('intermediate_field_mapping')
