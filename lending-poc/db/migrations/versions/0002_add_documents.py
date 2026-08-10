"""add documents

Revision ID: 0002_add_documents
Revises: 0001_add_cases
Create Date: 2026-08-10 11:51:33.283278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_documents"
down_revision: Union[str, None] = "0001_add_cases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column(
            "doc_type",
            sa.Enum("AADHAAR", "PAN", "ADDRESS_PROOF", "SALARY_SLIP", "BANK_STATEMENT", name="doc_type"),
            nullable=False,
        ),
        sa.Column("extracted_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_file_ref", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_case_id"), "documents", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_case_id"), table_name="documents")
    op.drop_table("documents")
    op.execute("DROP TYPE IF EXISTS doc_type")
