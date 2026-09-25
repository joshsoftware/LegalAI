"""drop address_embedding and the pgvector extension

Address embeddings were write-only: build_golden_record computed a vector on
every case and persistence stored it, but nothing ever read the column back
(the ADDRESS validation check that would have used it was removed, and
pgvector similarity search was never built). Storing them cost a
sentence-transformers model load per process and a 384-float column per case
for no consumer, so the whole layer is gone.

This migration is deliberately idempotent (DROP ... IF EXISTS):

  - Existing databases created the column in 0003 and get it dropped here.
  - Fresh databases never create it -- 0003 was edited to omit the column and
    0001 to omit `CREATE EXTENSION vector`, so the whole chain now replays on
    plain `postgres:16` instead of requiring the `pgvector/pgvector` image.

Editing already-applied migrations is normally a smell, but the alternative
was keeping the pgvector image forever purely so fresh installs could replay
a column they immediately drop. Both paths converge on the same schema.

Revision ID: 0010_drop_address_embedding
Revises: 0009_add_salary_continuity_check_type
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_drop_address_embedding"
down_revision: Union[str, None] = "0009_add_salary_continuity_check_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Column first: DROP EXTENSION fails while a column still uses the type.
    op.execute("ALTER TABLE golden_records DROP COLUMN IF EXISTS address_embedding")
    op.execute("DROP EXTENSION IF EXISTS vector")


def downgrade() -> None:
    # Restores the shape, NOT the data -- the stored vectors are gone for good.
    # Re-populating means recomputing every embedding from golden_records.address,
    # which needs the sentence-transformers code this change also deleted.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE golden_records ADD COLUMN IF NOT EXISTS address_embedding vector(384)")
