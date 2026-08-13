import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class CaseStatus(str, Enum):
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_ref: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    status: Mapped[CaseStatus] = mapped_column(
        SAEnum(CaseStatus, name="case_status"), nullable=False, default=CaseStatus.RECEIVED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    golden_record: Mapped["GoldenRecord | None"] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    validation_results: Mapped[list["ValidationResult"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    pipeline_results: Mapped[list["PipelineResult"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
