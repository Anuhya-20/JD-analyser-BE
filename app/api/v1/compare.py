"""
Candidate comparison API endpoint.
"""
from __future__ import annotations
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.database import get_db
from app.models.job_description import JobDescription
from app.models.candidate_profile import CandidateProfile
from app.models.match_result import MatchResult, MatchStatus
from app.models.recommendation import Recommendation
from app.models.hr_user import HRUser
from app.core.deps import get_current_hr_user
from app.schemas.compare import (
    CandidateCompareItem,
    CandidateScores,
    ComparisonInsights,
    CompareResponse,
)

router = APIRouter()


@router.get("", response_model=CompareResponse)
async def compare_candidates(
    jd_id: uuid.UUID = Query(..., description="Job Description ID"),
    profile_ids: List[uuid.UUID] = Query(..., description="2–4 CandidateProfile IDs to compare"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Side-by-side comparison of 2–4 candidates for a given job.
    Returns per-dimension scores, which candidate wins each dimension,
    shared skills, and skills unique to each candidate.
    """
    if len(profile_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 profile_ids to compare")
    if len(profile_ids) > 4:
        raise HTTPException(status_code=400, detail="Maximum 4 candidates can be compared at once")

    # Validate JD exists
    jd_result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = jd_result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    # Bulk load candidate profiles
    cp_result = await db.execute(
        select(CandidateProfile).where(CandidateProfile.id.in_(profile_ids))
    )
    profiles = {str(cp.id): cp for cp in cp_result.scalars().all()}

    missing = [str(pid) for pid in profile_ids if str(pid) not in profiles]
    if missing:
        raise HTTPException(status_code=404, detail=f"Profiles not found: {missing}")

    # Bulk load match results
    mr_result = await db.execute(
        select(MatchResult).where(
            MatchResult.candidate_profile_id.in_(profile_ids),
            MatchResult.job_description_id == jd_id,
        )
    )
    match_results = {str(mr.candidate_profile_id): mr for mr in mr_result.scalars().all()}

    if not match_results:
        raise HTTPException(
            status_code=400,
            detail="No match results found. Run the pipeline first.",
        )

    # Bulk load recommendations
    mr_ids = [mr.id for mr in match_results.values()]
    rec_result = await db.execute(
        select(Recommendation).where(Recommendation.match_result_id.in_(mr_ids))
    )
    recs_by_mr = {str(r.match_result_id): r for r in rec_result.scalars().all()}

    # Build per-candidate data
    ordered = [str(pid) for pid in profile_ids if str(pid) in match_results]

    # Collect scores per dimension for win computation
    dim_scores: dict[str, dict[str, Optional[float]]] = {
        "overall": {},
        "skill_match": {},
        "experience": {},
        "education": {},
        "semantic_similarity": {},
    }

    items_data = []
    for pid_str in ordered:
        profile = profiles[pid_str]
        mr = match_results[pid_str]
        rec = recs_by_mr.get(str(mr.id))

        dim_scores["overall"][pid_str] = mr.overall_score
        dim_scores["skill_match"][pid_str] = mr.skill_match_score
        dim_scores["experience"][pid_str] = mr.experience_score
        dim_scores["education"][pid_str] = mr.education_score
        dim_scores["semantic_similarity"][pid_str] = mr.semantic_similarity_score

        items_data.append({
            "pid_str": pid_str,
            "profile": profile,
            "mr": mr,
            "rec": rec,
        })

    def _winner(scores: dict[str, Optional[float]]) -> Optional[str]:
        valid = {k: v for k, v in scores.items() if v is not None}
        if not valid:
            return None
        return max(valid, key=lambda k: valid[k])

    dim_winners = {dim: _winner(scores) for dim, scores in dim_scores.items()}

    # Build unique skills per candidate
    all_matched: list[set[str]] = []
    for d in items_data:
        ms = set(s.lower() for s in (d["mr"].matched_skills or []))
        all_matched.append(ms)

    common_matched = set.intersection(*all_matched) if all_matched else set()

    # Build unique_skills: skills this candidate has that no one else has
    all_profile_skills: list[set[str]] = [
        set(s.lower() for s in (d["profile"].skills or []))
        for d in items_data
    ]

    dim_label_map = {
        "overall": "Overall Score",
        "skill_match": "Skill Match",
        "experience": "Experience",
        "education": "Education",
        "semantic_similarity": "Semantic Fit",
    }

    candidates: list[CandidateCompareItem] = []
    for i, d in enumerate(items_data):
        pid_str = d["pid_str"]
        profile = d["profile"]
        mr = d["mr"]
        rec = d["rec"]

        # Which dimensions does this candidate win?
        wins_on = [
            dim_label_map[dim]
            for dim, winner in dim_winners.items()
            if winner == pid_str
        ]

        # Skills unique to this candidate (not in any other candidate's profile)
        my_skills = all_profile_skills[i]
        others_union: set[str] = set()
        for j, skills in enumerate(all_profile_skills):
            if j != i:
                others_union |= skills
        unique_skills = sorted(my_skills - others_union)

        candidates.append(
            CandidateCompareItem(
                candidate_profile_id=profile.id,
                resume_id=profile.resume_id,
                full_name=profile.full_name,
                email=profile.email,
                location=profile.location,
                total_years_experience=profile.total_years_experience,
                highest_education_level=profile.highest_education_level,
                rank=mr.rank,
                scores=CandidateScores(
                    overall_score=mr.overall_score or 0.0,
                    skill_match_score=mr.skill_match_score,
                    experience_score=mr.experience_score,
                    education_score=mr.education_score,
                    semantic_similarity_score=mr.semantic_similarity_score,
                ),
                matched_skills=mr.matched_skills or [],
                missing_skills=mr.missing_skills or [],
                unique_skills=unique_skills,
                strengths=mr.strengths or [],
                weaknesses=mr.weaknesses or [],
                analysis_summary=mr.analysis_summary,
                recommendation_level=rec.level.value if rec else None,
                interview_questions=rec.interview_questions if rec else None,
                red_flags=rec.red_flags if rec else None,
                highlight_points=rec.highlight_points if rec else None,
                wins_on=wins_on,
            )
        )

    # JD required skills missing from ALL candidates
    jd_required = set(s.lower() for s in (jd.required_skills or []))
    matched_by_anyone: set[str] = set()
    for d in items_data:
        matched_by_anyone |= set(s.lower() for s in (d["mr"].matched_skills or []))
    missing_from_all = sorted(jd_required - matched_by_anyone)

    # Best candidates by dimension
    def _name_of(pid_str: Optional[str]) -> Optional[str]:
        if pid_str is None:
            return None
        return profiles[pid_str].full_name or f"Candidate {pid_str[:8]}"

    insights = ComparisonInsights(
        best_overall=_name_of(dim_winners.get("overall")),
        best_skill_match=_name_of(dim_winners.get("skill_match")),
        most_experienced=_name_of(
            max(
                {pid: (profiles[pid].total_years_experience or 0.0) for pid in ordered},
                key=lambda k: profiles[k].total_years_experience or 0.0,
            )
        ),
        common_matched_skills=sorted(common_matched),
        missing_from_all=missing_from_all,
    )

    logger.info(f"[Compare] JD={jd_id} compared {len(candidates)} candidates")

    return CompareResponse(
        job_description_id=jd_id,
        job_title=jd.title,
        company_name=jd.company_name,
        candidates=candidates,
        insights=insights,
    )
