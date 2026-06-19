"""
Dashboard API — recruiter-facing results view.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, cast, Date
from loguru import logger

from app.database import get_db
from app.models.job_description import JobDescription, JDStatus
from app.models.resume import Resume, ResumeStatus
from app.models.hr_user import HRUser
from app.core.deps import get_current_hr_user
from app.models.candidate_profile import CandidateProfile, CandidateStatus
from app.models.match_result import MatchResult, MatchStatus
from app.models.recommendation import Recommendation
from app.schemas.dashboard import (
    DashboardResponse,
    CandidateSummary,
    GlobalDashboardResponse,
    WeeklyActivityItem,
    PipelineStage,
    ScoreDistribution,
    PipelineStatusResponse,
)
from app.schemas.match_result import RankedCandidateResponse

router = APIRouter()


@router.get("/overview", response_model=GlobalDashboardResponse)
async def get_global_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Global dashboard — all stats across all JDs, no JD filter required."""
    now = datetime.now(timezone.utc)
    this_month_start = now - timedelta(days=30)
    last_month_start = now - timedelta(days=60)
    week_start = now - timedelta(days=7)

    # ── Total candidates (this month vs last month) ────────────────────────────
    total_candidates = (await db.execute(
        select(func.count(CandidateProfile.id))
    )).scalar_one()

    this_month_candidates = (await db.execute(
        select(func.count(CandidateProfile.id)).where(CandidateProfile.created_at >= this_month_start)
    )).scalar_one()

    last_month_candidates = (await db.execute(
        select(func.count(CandidateProfile.id)).where(
            CandidateProfile.created_at >= last_month_start,
            CandidateProfile.created_at < this_month_start,
        )
    )).scalar_one()

    candidates_change_pct = None
    if last_month_candidates > 0:
        candidates_change_pct = round((this_month_candidates - last_month_candidates) / last_month_candidates * 100, 1)

    # ── Active jobs & new this week ────────────────────────────────────────────
    active_jobs = (await db.execute(
        select(func.count(JobDescription.id)).where(JobDescription.is_active == True)  # noqa: E712
    )).scalar_one()

    new_jobs_this_week = (await db.execute(
        select(func.count(JobDescription.id)).where(
            JobDescription.is_active == True,  # noqa: E712
            JobDescription.created_at >= week_start,
        )
    )).scalar_one()

    # ── Shortlisted (accepted) ─────────────────────────────────────────────────
    shortlisted = (await db.execute(
        select(func.count(CandidateProfile.id)).where(
            CandidateProfile.status == CandidateStatus.ACCEPTED
        )
    )).scalar_one()

    shortlist_rate = round(shortlisted / total_candidates * 100, 1) if total_candidates > 0 else 0.0

    # ── Avg match score (this month vs last month) ─────────────────────────────
    avg_score = (await db.execute(
        select(func.avg(MatchResult.overall_score)).where(
            MatchResult.status == MatchStatus.COMPLETED,
            MatchResult.overall_score.isnot(None),
        )
    )).scalar_one_or_none()

    avg_score_this_month = (await db.execute(
        select(func.avg(MatchResult.overall_score)).where(
            MatchResult.status == MatchStatus.COMPLETED,
            MatchResult.overall_score.isnot(None),
            MatchResult.created_at >= this_month_start,
        )
    )).scalar_one_or_none()

    avg_score_last_month = (await db.execute(
        select(func.avg(MatchResult.overall_score)).where(
            MatchResult.status == MatchStatus.COMPLETED,
            MatchResult.overall_score.isnot(None),
            MatchResult.created_at >= last_month_start,
            MatchResult.created_at < this_month_start,
        )
    )).scalar_one_or_none()

    score_change_pct = None
    if avg_score_last_month and avg_score_this_month:
        score_change_pct = round((float(avg_score_this_month) - float(avg_score_last_month)) / float(avg_score_last_month) * 100, 1)

    # ── Weekly activity (last 7 days) ──────────────────────────────────────────
    resumes_by_day = (await db.execute(
        select(
            cast(Resume.created_at, Date).label("day"),
            func.count(Resume.id).label("cnt"),
        )
        .where(Resume.created_at >= week_start)
        .group_by(cast(Resume.created_at, Date))
    )).all()

    matches_by_day = (await db.execute(
        select(
            cast(MatchResult.created_at, Date).label("day"),
            func.count(MatchResult.id).label("cnt"),
        )
        .where(
            MatchResult.created_at >= week_start,
            MatchResult.status == MatchStatus.COMPLETED,
        )
        .group_by(cast(MatchResult.created_at, Date))
    )).all()

    shortlisted_by_day = (await db.execute(
        select(
            cast(CandidateProfile.updated_at, Date).label("day"),
            func.count(CandidateProfile.id).label("cnt"),
        )
        .where(
            CandidateProfile.updated_at >= week_start,
            CandidateProfile.status == CandidateStatus.ACCEPTED,
        )
        .group_by(cast(CandidateProfile.updated_at, Date))
    )).all()

    resume_map = {str(r.day): r.cnt for r in resumes_by_day}
    match_map = {str(m.day): m.cnt for m in matches_by_day}
    shortlist_map = {str(s.day): s.cnt for s in shortlisted_by_day}

    DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly_activity = []
    for i in range(6, -1, -1):
        day_dt = (now - timedelta(days=i)).date()
        day_str = str(day_dt)
        weekly_activity.append(WeeklyActivityItem(
            day=DAY_NAMES[day_dt.weekday()],
            date=day_str,
            resumes=resume_map.get(day_str, 0),
            matches=match_map.get(day_str, 0),
            shortlisted=shortlist_map.get(day_str, 0),
        ))

    # ── Candidate pipeline ─────────────────────────────────────────────────────
    total_resumes = (await db.execute(select(func.count(Resume.id)))).scalar_one()

    screened = (await db.execute(
        select(func.count(Resume.id)).where(Resume.status != ResumeStatus.PENDING)
    )).scalar_one()

    matched = (await db.execute(
        select(func.count(MatchResult.id)).where(MatchResult.status == MatchStatus.COMPLETED)
    )).scalar_one()

    pipeline = [
        PipelineStage(stage="Applied",     count=total_resumes),
        PipelineStage(stage="Screened",    count=screened),
        PipelineStage(stage="Matched",     count=matched),
        PipelineStage(stage="Shortlisted", count=shortlisted),
    ]

    return GlobalDashboardResponse(
        total_candidates=total_candidates,
        total_candidates_change_pct=candidates_change_pct,
        active_jobs=active_jobs,
        new_jobs_this_week=new_jobs_this_week,
        shortlisted=shortlisted,
        shortlist_rate=shortlist_rate,
        avg_match_score=round(float(avg_score), 2) if avg_score else None,
        avg_match_score_change_pct=score_change_pct,
        weekly_activity=weekly_activity,
        pipeline=pipeline,
    )


@router.get("/{jd_id}", response_model=DashboardResponse)
async def get_dashboard(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Recruiter dashboard: ALL ranked candidates with full match analysis and recommendations.
    Returns every processed resume ranked from best to worst — no artificial top-N cutoff.
    """
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    if jd.status not in (JDStatus.COMPLETED, JDStatus.ANALYZING):
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline not run yet. Current status: {jd.status.value}",
        )

    # Resume counts — single aggregated query
    counts = await db.execute(
        select(
            func.count(Resume.id).label("total"),
            func.count(case((Resume.status == ResumeStatus.COMPLETED, Resume.id))).label("completed"),
            func.count(case((Resume.status == ResumeStatus.FAILED, Resume.id))).label("failed"),
        ).where(Resume.job_description_id == jd_id)
    )
    cnt = counts.one()
    total_resumes = cnt.total or 0
    processed_resumes = cnt.completed or 0
    failed_resumes = cnt.failed or 0

    # ── Load ALL match results (no limit) ──────────────────────────────────────
    mr_result = await db.execute(
        select(MatchResult)
        .where(
            MatchResult.job_description_id == jd_id,
            MatchResult.status == MatchStatus.COMPLETED,
        )
        .order_by(MatchResult.rank.asc())
    )
    match_results = mr_result.scalars().all()

    if not match_results:
        return DashboardResponse(
            job_description_id=jd.id,
            job_title=jd.title,
            company_name=jd.company_name,
            status=jd.status.value,
            total_resumes=total_resumes,
            processed_resumes=processed_resumes,
            failed_resumes=failed_resumes,
            top_candidates=[],
            score_distribution=[],
            avg_overall_score=None,
            avg_experience_years=None,
            top_matched_skills=[],
            processing_completed_at=jd.updated_at if jd.status == JDStatus.COMPLETED else None,
            created_at=jd.created_at,
        )

    # ── Bulk load profiles — ONE query instead of N ────────────────────────────
    profile_ids = [mr.candidate_profile_id for mr in match_results]
    cp_result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.id.in_(profile_ids))
    )
    profiles_by_id: Dict[str, CandidateProfile] = {
        str(cp.id): cp for cp in cp_result.scalars().all()
    }

    # ── Bulk load recommendations — ONE query instead of N ─────────────────────
    mr_ids = [mr.id for mr in match_results]
    rec_result = await db.execute(
        select(Recommendation).where(Recommendation.match_result_id.in_(mr_ids))
    )
    recs_by_mr: Dict[str, Recommendation] = {
        str(r.match_result_id): r for r in rec_result.scalars().all()
    }

    # ── Build candidate summaries ──────────────────────────────────────────────
    candidates: List[CandidateSummary] = []
    all_skills: List[str] = []
    scores: List[float] = []

    for mr in match_results:
        profile = profiles_by_id.get(str(mr.candidate_profile_id))
        if not profile:
            continue
        rec = recs_by_mr.get(str(mr.id))

        if profile.skills:
            all_skills.extend(profile.skills)
        if mr.overall_score is not None:
            scores.append(mr.overall_score)

        candidates.append(
            CandidateSummary(
                rank=mr.rank or 0,
                candidate_profile_id=profile.id,
                resume_id=profile.resume_id,
                full_name=profile.full_name,
                email=profile.email,
                location=profile.location,
                total_years_experience=profile.total_years_experience,
                highest_education_level=profile.highest_education_level,
                skills=profile.skills,
                overall_score=mr.overall_score or 0.0,
                skill_match_score=mr.skill_match_score,
                experience_score=mr.experience_score,
                education_score=mr.education_score,
                semantic_similarity_score=mr.semantic_similarity_score,
                strengths=mr.strengths,
                weaknesses=mr.weaknesses,
                matched_skills=mr.matched_skills,
                missing_skills=mr.missing_skills,
                analysis_summary=mr.analysis_summary,
                recommendation_level=rec.level.value if rec else None,
                interview_questions=rec.interview_questions if rec else None,
                recruiter_notes=rec.recruiter_notes if rec else None,
                highlight_points=rec.highlight_points if rec else None,
                red_flags=rec.red_flags if rec else None,
            )
        )

    score_dist = _compute_score_distribution(scores)

    skill_counter = Counter(all_skills)
    top_skills = [
        {
            "skill": skill,
            "count": count,
            "percentage": round(count / max(len(match_results), 1) * 100, 1),
        }
        for skill, count in skill_counter.most_common(20)
    ]

    avg_score = round(sum(scores) / len(scores), 2) if scores else None

    exp_result = await db.execute(
        select(func.avg(CandidateProfile.total_years_experience)).where(
            CandidateProfile.job_description_id == jd_id
        )
    )
    avg_exp = exp_result.scalar_one_or_none()

    return DashboardResponse(
        job_description_id=jd.id,
        job_title=jd.title,
        company_name=jd.company_name,
        status=jd.status.value,
        total_resumes=total_resumes,
        processed_resumes=processed_resumes,
        failed_resumes=failed_resumes,
        top_candidates=candidates,
        score_distribution=score_dist,
        avg_overall_score=avg_score,
        avg_experience_years=round(float(avg_exp), 1) if avg_exp else None,
        top_matched_skills=top_skills,
        processing_completed_at=jd.updated_at if jd.status == JDStatus.COMPLETED else None,
        created_at=jd.created_at,
    )


@router.get("/{jd_id}/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Check the real-time status of the processing pipeline."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Single aggregated query for resume counts
    counts = await db.execute(
        select(
            func.count(Resume.id).label("total"),
            func.count(case((Resume.status == ResumeStatus.COMPLETED, Resume.id))).label("completed"),
            func.count(case((Resume.status == ResumeStatus.FAILED, Resume.id))).label("failed"),
        ).where(Resume.job_description_id == jd_id)
    )
    cnt = counts.one()
    total = cnt.total or 0
    completed = cnt.completed or 0
    failed = cnt.failed or 0

    profiled_result = await db.execute(
        select(func.count()).where(CandidateProfile.job_description_id == jd_id)
    )
    profiled = profiled_result.scalar_one()

    matched_result = await db.execute(
        select(func.count()).where(
            MatchResult.job_description_id == jd_id,
            MatchResult.status == MatchStatus.COMPLETED,
        )
    )
    matched = matched_result.scalar_one()

    rec_result = await db.execute(
        select(func.count())
        .select_from(Recommendation)
        .join(MatchResult, Recommendation.match_result_id == MatchResult.id)
        .where(MatchResult.job_description_id == jd_id)
    )
    recommended = rec_result.scalar_one()

    progress = round((completed / total * 100), 1) if total > 0 else 0.0

    return PipelineStatusResponse(
        job_description_id=jd.id,
        status=jd.status.value,
        total_resumes=total,
        parsed=completed + failed,
        profiled=profiled,
        matched=matched,
        ranked=matched,
        recommended=recommended,
        failed=failed,
        progress_percentage=progress,
        estimated_completion_seconds=None,
        error_message=jd.error_message,
    )


@router.get("/{jd_id}/candidates", response_model=List[RankedCandidateResponse])
async def get_ranked_candidates(
    jd_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Get paginated ranked candidates. page_size=50 default shows all for typical uploads."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    mr_result = await db.execute(
        select(MatchResult)
        .where(
            MatchResult.job_description_id == jd_id,
            MatchResult.status == MatchStatus.COMPLETED,
            MatchResult.overall_score >= min_score,
        )
        .order_by(MatchResult.rank.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    match_results = mr_result.scalars().all()

    if not match_results:
        return []

    # Bulk load profiles and recommendations
    profile_ids = [mr.candidate_profile_id for mr in match_results]
    cp_result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.id.in_(profile_ids))
    )
    profiles_by_id = {str(cp.id): cp for cp in cp_result.scalars().all()}

    mr_ids = [mr.id for mr in match_results]
    rec_result = await db.execute(
        select(Recommendation).where(Recommendation.match_result_id.in_(mr_ids))
    )
    recs_by_mr = {str(r.match_result_id): r for r in rec_result.scalars().all()}

    candidates = []
    for mr in match_results:
        profile = profiles_by_id.get(str(mr.candidate_profile_id))
        if not profile:
            continue
        rec = recs_by_mr.get(str(mr.id))

        rec_data = None
        if rec:
            rec_data = {
                "level": rec.level.value,
                "recruiter_notes": rec.recruiter_notes,
                "interview_questions": rec.interview_questions,
                "suggested_interview_stages": rec.suggested_interview_stages,
                "red_flags": rec.red_flags,
                "highlight_points": rec.highlight_points,
                "culture_fit_notes": rec.culture_fit_notes,
            }

        candidates.append(
            RankedCandidateResponse(
                rank=mr.rank or 0,
                overall_score=mr.overall_score or 0.0,
                candidate_profile={
                    "id": str(profile.id),
                    "full_name": profile.full_name,
                    "email": profile.email,
                    "location": profile.location,
                    "total_years_experience": profile.total_years_experience,
                    "skills": profile.skills,
                    "highest_education_level": profile.highest_education_level,
                },
                match_result={
                    "id": str(mr.id),
                    "overall_score": mr.overall_score,
                    "skill_match_score": mr.skill_match_score,
                    "experience_score": mr.experience_score,
                    "education_score": mr.education_score,
                    "semantic_similarity_score": mr.semantic_similarity_score,
                    "strengths": mr.strengths,
                    "weaknesses": mr.weaknesses,
                    "matched_skills": mr.matched_skills,
                    "missing_skills": mr.missing_skills,
                    "analysis_summary": mr.analysis_summary,
                },
                recommendation=rec_data,
            )
        )

    return candidates


def _compute_score_distribution(scores: List[float]) -> List[ScoreDistribution]:
    if not scores:
        return []

    total = len(scores)
    bins = [
        ("90-100", 90, 100),
        ("80-89", 80, 90),
        ("70-79", 70, 80),
        ("60-69", 60, 70),
        ("50-59", 50, 60),
        ("40-49", 40, 50),
        ("0-39", 0, 40),
    ]

    dist = []
    for label, low, high in bins:
        count = sum(1 for s in scores if low <= s < high or (high == 100 and s == 100))
        pct = round(count / total * 100, 1) if total > 0 else 0.0
        if count > 0:
            dist.append(ScoreDistribution(range=label, count=count, percentage=pct))

    return dist
