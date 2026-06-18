"""
Analytics / Graph API — chart-ready data for the recruiter dashboard.
"""
from __future__ import annotations
import uuid
from collections import Counter
from typing import List, Optional

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
    ScoreDistributionResponse,
    ScoreComponentsResponse,
    ScoreComponentStat,
    RecommendationBreakdownResponse,
    SkillAnalysisResponse,
    SkillEntry,
    CandidateTiersResponse,
    ExperienceDistributionResponse,
    ExperienceBucket,
    LabelCount,
)

router = APIRouter()


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total > 0 else 0.0


async def _get_completed_matches(db: AsyncSession, jd_id: uuid.UUID) -> List[MatchResult]:
    result = await db.execute(
        select(MatchResult).where(
            MatchResult.job_description_id == jd_id,
            MatchResult.status == MatchStatus.COMPLETED,
        )
    )
    return result.scalars().all()


async def _jd_or_404(db: AsyncSession, jd_id: uuid.UUID):
    jd = (await db.execute(select(JobDescription).where(JobDescription.id == jd_id))).scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    return jd


# ── 1. Score distribution ──────────────────────────────────────────────────────

@router.get("/{jd_id}/score-distribution", response_model=ScoreDistributionResponse)
async def score_distribution(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Bar chart — how many candidates fall in each score band (0-39, 40-49 … 90-100).
    """
    await _jd_or_404(db, jd_id)
    matches = await _get_completed_matches(db, jd_id)
    scores = [m.overall_score for m in matches if m.overall_score is not None]
    total = len(scores)

    bands = [
        ("90-100", 90, 101),
        ("80-89",  80,  90),
        ("70-79",  70,  80),
        ("60-69",  60,  70),
        ("50-59",  50,  60),
        ("40-49",  40,  50),
        ("0-39",    0,  40),
    ]
    ranges = []
    for label, lo, hi in bands:
        cnt = sum(1 for s in scores if lo <= s < hi)
        if cnt > 0:
            ranges.append(LabelCount(label=label, count=cnt, percentage=_pct(cnt, total)))

    avg = round(sum(scores) / total, 2) if scores else None
    return ScoreDistributionResponse(ranges=ranges, total_candidates=total, avg_score=avg)


# ── 2. Score components (radar chart) ─────────────────────────────────────────

@router.get("/{jd_id}/score-components", response_model=ScoreComponentsResponse)
async def score_components(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Radar / spider chart — average, min, max for each scoring dimension.
    """
    await _jd_or_404(db, jd_id)
    matches = await _get_completed_matches(db, jd_id)
    total = len(matches)

    def stats(values: List[Optional[float]]) -> tuple:
        vals = [v for v in values if v is not None]
        if not vals:
            return None, None, None
        return round(sum(vals) / len(vals), 2), round(max(vals), 2), round(min(vals), 2)

    dims = [
        ("skill_match",         "Skill Match",          [m.skill_match_score         for m in matches]),
        ("experience",          "Experience",            [m.experience_score          for m in matches]),
        ("education",           "Education",             [m.education_score           for m in matches]),
        ("semantic_similarity", "Semantic Similarity",   [m.semantic_similarity_score for m in matches]),
        ("keyword_match",       "Keyword Match",         [m.keyword_match_score       for m in matches]),
    ]

    components = []
    for name, label, vals in dims:
        avg, mx, mn = stats(vals)
        components.append(ScoreComponentStat(name=name, label=label, average=avg, maximum=mx, minimum=mn))

    overall_vals = [m.overall_score for m in matches if m.overall_score is not None]
    overall_avg = round(sum(overall_vals) / len(overall_vals), 2) if overall_vals else None

    return ScoreComponentsResponse(components=components, overall_average=overall_avg, total_candidates=total)


# ── 3. Recommendation breakdown (donut chart) ─────────────────────────────────

@router.get("/{jd_id}/recommendation-breakdown", response_model=RecommendationBreakdownResponse)
async def recommendation_breakdown(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Donut / pie chart — count per recommendation level.
    """
    await _jd_or_404(db, jd_id)
    matches = await _get_completed_matches(db, jd_id)
    total = len(matches)

    level_counts: Counter = Counter()
    for mr in matches:
        rec = (await db.execute(
            select(Recommendation).where(Recommendation.match_result_id == mr.id)
        )).scalar_one_or_none()
        level_counts[rec.level.value if rec else "no_recommendation"] += 1

    level_order = ["strongly_recommended", "recommended", "maybe", "not_recommended", "no_recommendation"]
    label_map = {
        "strongly_recommended": "Strongly Recommended",
        "recommended":          "Recommended",
        "maybe":                "Maybe",
        "not_recommended":      "Not Recommended",
        "no_recommendation":    "No Recommendation",
    }

    levels = [
        LabelCount(label=label_map.get(k, k), count=level_counts[k], percentage=_pct(level_counts[k], total))
        for k in level_order if level_counts[k] > 0
    ]
    return RecommendationBreakdownResponse(levels=levels, total=total)


# ── 4. Skill analysis (bar chart) ─────────────────────────────────────────────

@router.get("/{jd_id}/skill-analysis", response_model=SkillAnalysisResponse)
async def skill_analysis(
    jd_id: uuid.UUID,
    top_n: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Horizontal bar charts:
    - Top N most-matched skills (skills candidates HAVE that the JD wants)
    - Top N most-missing skills (JD requirements candidates LACK)
    """
    await _jd_or_404(db, jd_id)
    matches = await _get_completed_matches(db, jd_id)
    total = len(matches)

    matched_counter: Counter = Counter()
    missing_counter: Counter = Counter()
    total_matched = 0
    total_missing = 0

    for mr in matches:
        for s in (mr.matched_skills or []):
            matched_counter[s.strip()] += 1
            total_matched += 1
        for s in (mr.missing_skills or []):
            missing_counter[s.strip()] += 1
            total_missing += 1

    top_matched = [
        SkillEntry(skill=sk, candidate_count=cnt, percentage=_pct(cnt, total))
        for sk, cnt in matched_counter.most_common(top_n)
    ]
    top_missing = [
        SkillEntry(skill=sk, candidate_count=cnt, percentage=_pct(cnt, total))
        for sk, cnt in missing_counter.most_common(top_n)
    ]

    return SkillAnalysisResponse(
        top_matched_skills=top_matched,
        top_missing_skills=top_missing,
        total_candidates=total,
        avg_matched_count=round(total_matched / total, 1) if total > 0 else 0.0,
        avg_missing_count=round(total_missing / total, 1) if total > 0 else 0.0,
    )


# ── 5. Candidate tiers (pie chart) ────────────────────────────────────────────

@router.get("/{jd_id}/candidate-tiers", response_model=CandidateTiersResponse)
async def candidate_tiers(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Pie chart — fresher vs experienced candidate split.
    """
    await _jd_or_404(db, jd_id)
    matches = await _get_completed_matches(db, jd_id)
    total = len(matches)

    tier_counts: Counter = Counter(mr.candidate_tier or "experienced" for mr in matches)

    label_map = {"fresher": "Fresher", "experienced": "Experienced"}
    tiers = [
        LabelCount(label=label_map.get(k, k.title()), count=v, percentage=_pct(v, total))
        for k, v in sorted(tier_counts.items(), key=lambda x: -x[1])
    ]
    return CandidateTiersResponse(tiers=tiers, total=total)


# ── 6. Experience distribution (histogram) ────────────────────────────────────

@router.get("/{jd_id}/experience-distribution", response_model=ExperienceDistributionResponse)
async def experience_distribution(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Histogram — distribution of candidates by years of experience.
    """
    await _jd_or_404(db, jd_id)
    matches = await _get_completed_matches(db, jd_id)
    total = len(matches)

    exp_values: list[float] = []
    for mr in matches:
        cp = (await db.execute(
            select(CandidateProfile).where(CandidateProfile.id == mr.candidate_profile_id)
        )).scalar_one_or_none()
        if cp and cp.total_years_experience is not None:
            exp_values.append(cp.total_years_experience)

    buckets_def = [
        ("0-2",  "0-2 yrs",   0,  2),
        ("2-5",  "2-5 yrs",   2,  5),
        ("5-8",  "5-8 yrs",   5,  8),
        ("8-12", "8-12 yrs",  8, 12),
        ("12+",  "12+ yrs",  12, 999),
    ]

    buckets = []
    for key, label, lo, hi in buckets_def:
        cnt = sum(1 for e in exp_values if lo <= e < hi)
        buckets.append(ExperienceBucket(
            range=key, label=label, count=cnt, percentage=_pct(cnt, len(exp_values))
        ))

    avg_y = round(sum(exp_values) / len(exp_values), 1) if exp_values else None
    return ExperienceDistributionResponse(
        buckets=buckets,
        avg_years=avg_y,
        max_years=max(exp_values) if exp_values else None,
        min_years=min(exp_values) if exp_values else None,
        total_candidates=total,
    )
