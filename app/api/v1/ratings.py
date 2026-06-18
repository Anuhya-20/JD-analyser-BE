"""
Candidate Rating API — per-JD score tables and individual breakdowns.
"""
from __future__ import annotations
import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.hr_user import HRUser
from app.models.job_description import JobDescription
from app.models.candidate_profile import CandidateProfile
from app.models.match_result import MatchResult, MatchStatus
from app.models.recommendation import Recommendation
from app.core.deps import get_current_hr_user
from app.schemas.analytics import (
    CandidateRatingItem,
    CandidateRatingListResponse,
    CandidateRatingDetail,
    ScoreComponentDetail,
)

router = APIRouter()

# Score weights used by the ranking agent (must mirror ranking_agent.py)
_WEIGHTS = {
    "skill_match":          0.35,
    "experience":           0.25,
    "education":            0.15,
    "semantic_similarity":  0.15,
    "keyword_match":        0.10,
}


def _safe(v: Optional[float]) -> float:
    return v if v is not None else 0.0


@router.get("/{jd_id}", response_model=CandidateRatingListResponse)
async def get_ratings(
    jd_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    sort_by: str = Query("rank", description="rank | overall_score | skill_match_score | experience_score"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Paginated ratings table — every score component for every candidate.
    Front-end can build a sortable leaderboard from this.
    """
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job description not found")

    sort_col = {
        "rank":                MatchResult.rank.asc(),
        "overall_score":       MatchResult.overall_score.desc(),
        "skill_match_score":   MatchResult.skill_match_score.desc(),
        "experience_score":    MatchResult.experience_score.desc(),
    }.get(sort_by, MatchResult.rank.asc())

    base_q = (
        select(MatchResult)
        .where(
            MatchResult.job_description_id == jd_id,
            MatchResult.status == MatchStatus.COMPLETED,
            MatchResult.overall_score >= min_score,
        )
    )

    count_result = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = count_result.scalar_one()

    mrs = (await db.execute(
        base_q.order_by(sort_col)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    items = []
    for mr in mrs:
        # Load profile for name/email/experience
        cp = (await db.execute(
            select(CandidateProfile).where(CandidateProfile.id == mr.candidate_profile_id)
        )).scalar_one_or_none()

        # Load recommendation level
        rec = (await db.execute(
            select(Recommendation).where(Recommendation.match_result_id == mr.id)
        )).scalar_one_or_none()

        items.append(CandidateRatingItem(
            rank=mr.rank or 0,
            candidate_profile_id=mr.candidate_profile_id,
            full_name=cp.full_name if cp else None,
            email=cp.email if cp else None,
            total_years_experience=cp.total_years_experience if cp else None,
            candidate_tier=mr.candidate_tier,
            overall_score=_safe(mr.overall_score),
            skill_match_score=mr.skill_match_score,
            experience_score=mr.experience_score,
            education_score=mr.education_score,
            semantic_similarity_score=mr.semantic_similarity_score,
            keyword_match_score=mr.keyword_match_score,
            matched_skills_count=len(mr.matched_skills or []),
            missing_skills_count=len(mr.missing_skills or []),
            recommendation_level=rec.level.value if rec else None,
            status=cp.status.value if cp else "pending",
        ))

    return CandidateRatingListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{jd_id}/candidate/{profile_id}", response_model=CandidateRatingDetail)
async def get_candidate_rating(
    jd_id: uuid.UUID,
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Full score breakdown for one candidate — suitable for a detail card or radar chart.
    Returns each score component with its weight and contribution to the overall score.
    """
    mr = (await db.execute(
        select(MatchResult).where(
            MatchResult.job_description_id == jd_id,
            MatchResult.candidate_profile_id == profile_id,
            MatchResult.status == MatchStatus.COMPLETED,
        )
    )).scalar_one_or_none()

    if not mr:
        raise HTTPException(status_code=404, detail="Rating not found for this candidate / JD combination")

    cp = (await db.execute(
        select(CandidateProfile).where(CandidateProfile.id == profile_id)
    )).scalar_one_or_none()

    rec = (await db.execute(
        select(Recommendation).where(Recommendation.match_result_id == mr.id)
    )).scalar_one_or_none()

    overall = _safe(mr.overall_score)

    score_breakdown = {
        "skill_match": ScoreComponentDetail(
            score=mr.skill_match_score,
            weight=_WEIGHTS["skill_match"],
            contribution=round(_safe(mr.skill_match_score) * _WEIGHTS["skill_match"] / 100, 2),
        ),
        "experience": ScoreComponentDetail(
            score=mr.experience_score,
            weight=_WEIGHTS["experience"],
            contribution=round(_safe(mr.experience_score) * _WEIGHTS["experience"] / 100, 2),
        ),
        "education": ScoreComponentDetail(
            score=mr.education_score,
            weight=_WEIGHTS["education"],
            contribution=round(_safe(mr.education_score) * _WEIGHTS["education"] / 100, 2),
        ),
        "semantic_similarity": ScoreComponentDetail(
            score=mr.semantic_similarity_score,
            weight=_WEIGHTS["semantic_similarity"],
            contribution=round(_safe(mr.semantic_similarity_score) * _WEIGHTS["semantic_similarity"] / 100, 2),
        ),
        "keyword_match": ScoreComponentDetail(
            score=mr.keyword_match_score,
            weight=_WEIGHTS["keyword_match"],
            contribution=round(_safe(mr.keyword_match_score) * _WEIGHTS["keyword_match"] / 100, 2),
        ),
    }

    return CandidateRatingDetail(
        rank=mr.rank,
        candidate_profile_id=profile_id,
        full_name=cp.full_name if cp else None,
        email=cp.email if cp else None,
        location=cp.location if cp else None,
        total_years_experience=cp.total_years_experience if cp else None,
        candidate_tier=mr.candidate_tier,
        overall_score=overall,
        score_breakdown=score_breakdown,
        matched_skills=mr.matched_skills,
        missing_skills=mr.missing_skills,
        strengths=mr.strengths,
        weaknesses=mr.weaknesses,
        analysis_summary=mr.analysis_summary,
        recommendation_level=rec.level.value if rec else None,
        recruiter_notes=rec.recruiter_notes if rec else None,
        interview_questions=rec.interview_questions if rec else None,
        suggested_interview_stages=rec.suggested_interview_stages if rec else None,
        red_flags=rec.red_flags if rec else None,
        highlight_points=rec.highlight_points if rec else None,
        culture_fit_notes=rec.culture_fit_notes if rec else None,
    )
