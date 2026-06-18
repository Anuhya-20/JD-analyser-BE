"""Add fresher support fields to candidate_profiles and match_results

Revision ID: 002
Revises: 001
Create Date: 2024-01-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # candidate_profiles — fresher fields
    op.add_column("candidate_profiles", sa.Column("internship_months", sa.Integer, nullable=True))
    op.add_column("candidate_profiles", sa.Column("gpa", sa.Float, nullable=True))
    op.add_column("candidate_profiles", sa.Column("is_fresher", sa.Boolean, nullable=False, server_default="false"))

    # match_results — candidate tier
    op.add_column("match_results", sa.Column("candidate_tier", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("match_results", "candidate_tier")
    op.drop_column("candidate_profiles", "is_fresher")
    op.drop_column("candidate_profiles", "gpa")
    op.drop_column("candidate_profiles", "internship_months")
