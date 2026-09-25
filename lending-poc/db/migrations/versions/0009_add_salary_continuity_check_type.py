"""add SALARY_CONTINUITY to check_type enum

Revision ID: 0009_add_salary_continuity_check_type
Revises: 0008_merge_heads
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_add_salary_continuity_check_type"
down_revision: Union[str, None] = "0008_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE check_type ADD VALUE IF NOT EXISTS 'SALARY_CONTINUITY'")


def downgrade() -> None:
    raise NotImplementedError(
        "Postgres cannot remove a value from an enum type without recreating it "
        "(dropping/recreating check_type would require rewriting the "
        "validation_results table's check_type column and re-adding its "
        "constraints/indexes). Downgrade intentionally unsupported for this "
        "migration."
    )
