from __future__ import annotations
import uuid
from typing import List, Optional
from pydantic import BaseModel


# ── Shared ────────────────────────────────────────────────────────────────────

class LabelCount(BaseModel):
    label: str
    count: int
    percentage: float


# ── Rating schemas ────────────────────────────────────────────────────────────

class CandidateRatingItem(BaseModel):
    """One row in the ratings table — every score component visible at a glance."""
    rank: int
    candidate_profile_id: uuid.UUID
    full_name: Optional[str]
    email: Optional[str]
    total_years_experience: Optional[float]
    candidate_tier: Optional[str]          # "fresher" | "experienced"
    overall_score: float
    skill_match_score: Optional[float]
    experience_score: Optional[float]
    education_score: Optional[float]
    semantic_similarity_score: Optional[float]
    keyword_match_score: Optional[float]
    matched_skills_count: int
    missing_skills_count: int
    recommendation_level: Optional[str]


class CandidateRatingListResponse(BaseModel):
    items: List[CandidateRatingItem]
    total: int
    page: int
    page_size: int
    pages: int


class ScoreComponentDetail(BaseModel):
    score: Optional[float]
    weight: float
    contribution: float           # score * weight / 100


class CandidateRatingDetail(BaseModel):
    """Full score breakdown for a single candidate."""
    rank: Optional[int]
    candidate_profile_id: uuid.UUID
    full_name: Optional[str]
    email: Optional[str]
    location: Optional[str]
    total_years_experience: Optional[float]
    candidate_tier: Optional[str]
    overall_score: float
    score_breakdown: dict[str, ScoreComponentDetail]
    matched_skills: Optional[List[str]]
    missing_skills: Optional[List[str]]
    strengths: Optional[List[str]]
    weaknesses: Optional[List[str]]
    analysis_summary: Optional[str]
    recommendation_level: Optional[str]
    recruiter_notes: Optional[str]
    interview_questions: Optional[List[str]]
    suggested_interview_stages: Optional[List[str]]
    red_flags: Optional[List[str]]
    highlight_points: Optional[List[str]]
    culture_fit_notes: Optional[str]


# ── Graph / Analytics schemas ─────────────────────────────────────────────────

class ScoreDistributionResponse(BaseModel):
    """Bar chart — how many candidates fall in each score band."""
    ranges: List[LabelCount]
    total_candidates: int
    avg_score: Optional[float]


class ScoreComponentStat(BaseModel):
    name: str
    label: str                    # human-readable axis label for radar chart
    average: Optional[float]
    maximum: Optional[float]
    minimum: Optional[float]


class ScoreComponentsResponse(BaseModel):
    """Radar / spider chart — average of each score dimension."""
    components: List[ScoreComponentStat]
    overall_average: Optional[float]
    total_candidates: int


class RecommendationBreakdownResponse(BaseModel):
    """Donut / pie chart — recommendation level distribution."""
    levels: List[LabelCount]
    total: int


class SkillEntry(BaseModel):
    skill: str
    candidate_count: int
    percentage: float


class SkillAnalysisResponse(BaseModel):
    """Bar chart — most matched and most-missing skills across all candidates."""
    top_matched_skills: List[SkillEntry]
    top_missing_skills: List[SkillEntry]
    total_candidates: int
    avg_matched_count: float
    avg_missing_count: float


class CandidateTiersResponse(BaseModel):
    """Pie chart — fresher vs experienced split."""
    tiers: List[LabelCount]
    total: int


class ExperienceBucket(BaseModel):
    range: str
    label: str
    count: int
    percentage: float


class ExperienceDistributionResponse(BaseModel):
    """Histogram — years-of-experience distribution."""
    buckets: List[ExperienceBucket]
    avg_years: Optional[float]
    max_years: Optional[float]
    min_years: Optional[float]
    total_candidates: int
