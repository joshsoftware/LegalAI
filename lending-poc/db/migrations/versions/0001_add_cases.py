"""add cases

Revision ID: 0001_add_cases
Revises:
Create Date: 2026-08-10 11:51:33.283278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_add_cases"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("applicant_ref", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("RECEIVED", "RUNNING", "PASS", "FAIL", "NEEDS_REVIEW", name="case_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cases_applicant_ref"), "cases", ["applicant_ref"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_applicant_ref"), table_name="cases")
    op.drop_table("cases")
    op.execute("DROP TYPE IF EXISTS case_status")
