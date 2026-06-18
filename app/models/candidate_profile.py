import uuid
from typing import Optional
from sqlalchemy import String, Text, ForeignKey, JSON, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin



class CandidateProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "candidate_profiles"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Personal info
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    portfolio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured profile data (JSON)
    skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    work_experience: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    education: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    certifications: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    projects: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    languages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    publications: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Computed metrics
    total_years_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    internship_months: Mapped[Optional[int]] = mapped_column(nullable=True)
    gpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_fresher: Mapped[bool] = mapped_column(default=False, nullable=False)
    highest_education_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Embedding stored as JSON array (no pgvector needed)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Relationships
    resume: Mapped["Resume"] = relationship("Resume", back_populates="candidate_profile")
    match_result: Mapped[Optional["MatchResult"]] = relationship(
        "MatchResult", back_populates="candidate_profile", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_candidate_profiles_job_description_id", "job_description_id"),
        Index("ix_candidate_profiles_email", "email"),
    )

    def __repr__(self) -> str:
        return f"<CandidateProfile id={self.id} name={self.full_name!r}>"
