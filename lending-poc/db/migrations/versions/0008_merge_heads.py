"""merge migration heads

Revision ID: 0008_merge_heads
Revises: 0006_doc_source_ref_nullable, 0006_create_intermediate_field_mapping_table
Create Date: 2026-09-08 12:41:48.938903

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_merge_heads'
down_revision: Union[str, None] = ('0006_doc_source_ref_nullable', '0006_create_intermediate_field_mapping_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
