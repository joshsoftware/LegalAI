"""add golden_records

Revision ID: 0003_add_golden_records
Revises: 0002_add_documents
Create Date: 2026-08-10 11:51:33.283278

NOTE: this originally created an `address_embedding` pgvector column. That
column was removed in 0010, and it is omitted here so a fresh database can
replay the whole chain on plain `postgres:16` rather than needing the
`pgvector/pgvector` image just to create a column 0010 immediately drops.
Databases created before 0010 still have the column; 0010 drops it with
`IF EXISTS`, so both paths end at the same schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import db.models.types

# revision identifiers, used by Alembic.
revision: str = "0003_add_golden_records"
down_revision: Union[str, None] = "0002_add_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "golden_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("aadhaar_number", db.models.types.EncryptedString(), nullable=True),
        sa.Column("pan_number", db.models.types.EncryptedString(), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
    )


def downgrade() -> None:
    op.drop_table("golden_records")
