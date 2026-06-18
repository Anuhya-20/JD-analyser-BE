import uuid
import enum
from typing import Optional
from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class ResumeStatus(str, enum.Enum):
    PENDING = "pending"
    PARSING = "parsing"
    PROFILING = "profiling"
    COMPLETED = "completed"
    FAILED = "failed"


class Resume(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "resumes"

    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # pdf, docx
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(nullable=True)

    status: Mapped[ResumeStatus] = mapped_column(
        SAEnum(ResumeStatus, values_callable=lambda x: [e.value for e in x]), default=ResumeStatus.PENDING, nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription", back_populates="resumes"
    )
    candidate_profile: Mapped[Optional["CandidateProfile"]] = relationship(
        "CandidateProfile", back_populates="resume", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_resumes_job_description_id", "job_description_id"),
        Index("ix_resumes_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} filename={self.original_filename!r}>"
