import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base
from db.models.types import EncryptedString

# Dimensionality of the BAAI/bge-small-en-v1.5 embedding used for address
# matching (app.matching.embeddings) — duplicated here as a plain constant
# so the DB models don't depend on the matching/ML package.
EMBEDDING_DIMENSIONS = 384


class GoldenRecord(Base):
    __tablename__ = "golden_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    address_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    aadhaar_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    pan_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    case: Mapped["Case"] = relationship(back_populates="golden_record")
