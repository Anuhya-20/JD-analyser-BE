import uuid
from typing import Optional
from sqlalchemy import Integer, ForeignKey, JSON, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin


class InterviewSession(Base, UUIDMixin, TimestampMixin):
    """
    Stores generated interview questions with direct FK relations to
    candidate, JD, match result, and the HR user who triggered generation.
    One session per (candidate_profile_id, job_description_id) pair —
    regenerating overwrites the previous session.
    """
    __tablename__ = "interview_sessions"

    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_description_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("match_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    technical_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    behavioral_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    scenario_questions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Optional label, e.g. "Round 1", "Final Round"
    round_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    candidate_profile: Mapped["CandidateProfile"] = relationship(
        "CandidateProfile", back_populates="interview_sessions"
    )
    job_description: Mapped["JobDescription"] = relationship(
        "JobDescription", back_populates="interview_sessions"
    )
    match_result: Mapped[Optional["MatchResult"]] = relationship(
        "MatchResult", back_populates="interview_sessions"
    )
    generated_by: Mapped[Optional["HRUser"]] = relationship(
        "HRUser", back_populates="interview_sessions"
    )

    __table_args__ = (
        Index("ix_interview_sessions_candidate", "candidate_profile_id"),
        Index("ix_interview_sessions_jd", "job_description_id"),
    )

    def __repr__(self) -> str:
        return f"<InterviewSession id={self.id} candidate={self.candidate_profile_id}>"
