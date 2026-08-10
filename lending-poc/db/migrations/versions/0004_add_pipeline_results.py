"""add pipeline_results

Revision ID: 0004_add_pipeline_results
Revises: 0003_add_golden_records
Create Date: 2026-08-10 11:51:33.283278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_add_pipeline_results"
down_revision: Union[str, None] = "0003_add_golden_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("decision", sa.Enum("PASS", "FAIL", "NEEDS_REVIEW", name="decision"), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reviewer", sa.String(), nullable=True),
        sa.Column(
            "review_status", sa.Enum("PENDING", "APPROVED", "REJECTED", name="review_status"), nullable=True
        ),
        sa.Column("reviewer_remarks", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_results_case_id"), "pipeline_results", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pipeline_results_case_id"), table_name="pipeline_results")
    op.drop_table("pipeline_results")
    op.execute("DROP TYPE IF EXISTS decision")
    op.execute("DROP TYPE IF EXISTS review_status")
