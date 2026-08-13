"""make document source_file_ref nullable

Revision ID: 0006_doc_source_ref_nullable
Revises: 0005_add_validation_results
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_doc_source_ref_nullable"
down_revision: Union[str, None] = "0005_add_validation_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("documents", "source_file_ref", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    op.alter_column("documents", "source_file_ref", existing_type=sa.String(), nullable=False)
