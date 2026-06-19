import uuid
import enum
from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, JSON, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class MatchStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class MatchResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "match_results"

    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Scores (0.0 - 100.0)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    skill_match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    experience_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    education_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    semantic_similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    keyword_match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Analysis
    strengths: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    matched_skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    missing_skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    analysis_summary: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    candidate_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # fresher | experienced
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[MatchStatus] = mapped_column(
        SAEnum(MatchStatus, values_callable=lambda x: [e.value for e in x]), default=MatchStatus.PENDING, nullable=False
    )

    # Relationships
    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription", back_populates="match_results"
    )
    candidate_profile: Mapped["CandidateProfile"] = relationship(
        "CandidateProfile", back_populates="match_result"
    )
    recommendation: Mapped[Optional["Recommendation"]] = relationship(
        "Recommendation", back_populates="match_result", uselist=False, cascade="all, delete-orphan"
    )
    interview_sessions: Mapped[list["InterviewSession"]] = relationship(
        "InterviewSession", back_populates="match_result"
    )

    __table_args__ = (
        Index("ix_match_results_job_description_id", "job_description_id"),
        Index("ix_match_results_overall_score", "overall_score"),
        Index("ix_match_results_rank", "rank"),
    )

    def __repr__(self) -> str:
        return f"<MatchResult id={self.id} score={self.overall_score} rank={self.rank}>"
