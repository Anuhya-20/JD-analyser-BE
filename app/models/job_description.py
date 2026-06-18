import uuid
import enum
from typing import Optional, List
from sqlalchemy import String, Text, Enum as SAEnum, JSON, Index, Boolean, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class JDStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobDescription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "job_descriptions"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Structured analysis from LLM
    required_skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    preferred_skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    experience_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    min_years_experience: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_years_experience: Mapped[Optional[float]] = mapped_column(nullable=True)
    education_requirements: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    responsibilities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    company_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    salary_range: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Embedding stored as JSON array (no pgvector needed)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    status: Mapped[JDStatus] = mapped_column(
        SAEnum(JDStatus, values_callable=lambda x: [e.value for e in x]), default=JDStatus.PENDING, nullable=False
    )
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("TRUE"), default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    resumes: Mapped[List["Resume"]] = relationship(
        "Resume", back_populates="job_description", cascade="all, delete-orphan"
    )
    match_results: Mapped[List["MatchResult"]] = relationship(
        "MatchResult", back_populates="job_description", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_job_descriptions_status", "status"),
        Index("ix_job_descriptions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<JobDescription id={self.id} title={self.title!r}>"
