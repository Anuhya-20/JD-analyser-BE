"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # job_descriptions
    op.create_table(
        "job_descriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("description_text", sa.Text, nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("required_skills", postgresql.JSON, nullable=True),
        sa.Column("preferred_skills", postgresql.JSON, nullable=True),
        sa.Column("experience_level", sa.String(100), nullable=True),
        sa.Column("min_years_experience", sa.Float, nullable=True),
        sa.Column("max_years_experience", sa.Float, nullable=True),
        sa.Column("education_requirements", postgresql.JSON, nullable=True),
        sa.Column("responsibilities", postgresql.JSON, nullable=True),
        sa.Column("company_context", sa.Text, nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("employment_type", sa.String(100), nullable=True),
        sa.Column("salary_range", postgresql.JSON, nullable=True),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("embedding", postgresql.JSON, nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "analyzing", "completed", "failed", name="jdstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_job_descriptions_status", "job_descriptions", ["status"])
    op.create_index("ix_job_descriptions_created_at", "job_descriptions", ["created_at"])

    # resumes
    op.create_table(
        "resumes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_description_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_descriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "parsing", "profiling", "completed", "failed", name="resumestatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_resumes_job_description_id", "resumes", ["job_description_id"])
    op.create_index("ix_resumes_status", "resumes", ["status"])

    # candidate_profiles
    op.create_table(
        "candidate_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "resume_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "job_description_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_descriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("github_url", sa.String(500), nullable=True),
        sa.Column("portfolio_url", sa.String(500), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("skills", postgresql.JSON, nullable=True),
        sa.Column("work_experience", postgresql.JSON, nullable=True),
        sa.Column("education", postgresql.JSON, nullable=True),
        sa.Column("certifications", postgresql.JSON, nullable=True),
        sa.Column("projects", postgresql.JSON, nullable=True),
        sa.Column("languages", postgresql.JSON, nullable=True),
        sa.Column("publications", postgresql.JSON, nullable=True),
        sa.Column("total_years_experience", sa.Float, nullable=True),
        sa.Column("highest_education_level", sa.String(100), nullable=True),
        sa.Column("embedding", postgresql.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_candidate_profiles_job_description_id", "candidate_profiles", ["job_description_id"]
    )
    op.create_index("ix_candidate_profiles_email", "candidate_profiles", ["email"])

    # match_results
    op.create_table(
        "match_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_description_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_descriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "candidate_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("overall_score", sa.Float, nullable=True),
        sa.Column("skill_match_score", sa.Float, nullable=True),
        sa.Column("experience_score", sa.Float, nullable=True),
        sa.Column("education_score", sa.Float, nullable=True),
        sa.Column("semantic_similarity_score", sa.Float, nullable=True),
        sa.Column("keyword_match_score", sa.Float, nullable=True),
        sa.Column("strengths", postgresql.JSON, nullable=True),
        sa.Column("weaknesses", postgresql.JSON, nullable=True),
        sa.Column("matched_skills", postgresql.JSON, nullable=True),
        sa.Column("missing_skills", postgresql.JSON, nullable=True),
        sa.Column("analysis_summary", sa.String(2000), nullable=True),
        sa.Column("rank", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "failed", name="matchstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_match_results_job_description_id", "match_results", ["job_description_id"])
    op.create_index("ix_match_results_overall_score", "match_results", ["overall_score"])
    op.create_index("ix_match_results_rank", "match_results", ["rank"])

    # recommendations
    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "match_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("match_results.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "level",
            sa.Enum(
                "strongly_recommended",
                "recommended",
                "maybe",
                "not_recommended",
                name="recommendationlevel",
            ),
            nullable=False,
        ),
        sa.Column("recruiter_notes", sa.Text, nullable=True),
        sa.Column("interview_questions", postgresql.JSON, nullable=True),
        sa.Column("suggested_interview_stages", postgresql.JSON, nullable=True),
        sa.Column("red_flags", postgresql.JSON, nullable=True),
        sa.Column("highlight_points", postgresql.JSON, nullable=True),
        sa.Column("culture_fit_notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("match_results")
    op.drop_table("candidate_profiles")
    op.drop_table("resumes")
    op.drop_table("job_descriptions")
    op.execute("DROP TYPE IF EXISTS recommendationlevel")
    op.execute("DROP TYPE IF EXISTS matchstatus")
    op.execute("DROP TYPE IF EXISTS resumestatus")
    op.execute("DROP TYPE IF EXISTS jdstatus")
