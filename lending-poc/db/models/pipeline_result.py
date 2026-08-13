"""DB model for a pipeline run.

Named `PipelineResult` to match the ERD/table name. If an in-memory DTO with
the same name is introduced elsewhere, import one or both qualified
(`from db.models import pipeline_result as pipeline_result_model`) in any
module that needs both.
"""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base
from db.models.enums import Decision


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PipelineResult(Base):
    __tablename__ = "pipeline_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[Decision] = mapped_column(SAEnum(Decision, name="decision"), nullable=False)
    reasons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String, nullable=True)
    review_status: Mapped[ReviewStatus | None] = mapped_column(
        SAEnum(ReviewStatus, name="review_status"), nullable=True
    )
    reviewer_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    case: Mapped["Case"] = relationship(back_populates="pipeline_results")
