"""add validation_results

Revision ID: 0005_add_validation_results
Revises: 0004_add_pipeline_results
Create Date: 2026-08-10 11:51:33.283278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_add_validation_results"
down_revision: Union[str, None] = "0004_add_pipeline_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validation_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column(
            "check_type",
            sa.Enum(
                "NAME",
                "ADDRESS",
                "AADHAAR",
                "PAN",
                "DOB",
                "EMPLOYER",
                "SALARY_DATE",
                "SALARY_CREDIT_COUNT",
                "MANDATORY_PRESENCE",
                name="check_type",
            ),
            nullable=False,
        ),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_validation_results_case_id"), "validation_results", ["case_id"], unique=False)
    op.create_index(
        op.f("ix_validation_results_document_id"), "validation_results", ["document_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_validation_results_document_id"), table_name="validation_results")
    op.drop_index(op.f("ix_validation_results_case_id"), table_name="validation_results")
    op.drop_table("validation_results")
    op.execute("DROP TYPE IF EXISTS check_type")
