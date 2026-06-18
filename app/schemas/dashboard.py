from __future__ import annotations
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class CandidateSummary(BaseModel):
    rank: int
    candidate_profile_id: uuid.UUID
    resume_id: uuid.UUID
    full_name: Optional[str]
    email: Optional[str]
    location: Optional[str]
    total_years_experience: Optional[float]
    internship_months: Optional[int] = 0
    gpa: Optional[float] = None
    is_fresher: bool = False
    candidate_tier: str = "experienced"          # "fresher" | "experienced"
    highest_education_level: Optional[str]
    skills: Optional[List[str]]
    overall_score: float
    skill_match_score: Optional[float]
    experience_score: Optional[float]
    education_score: Optional[float]
    semantic_similarity_score: Optional[float]
    strengths: Optional[List[str]]
    weaknesses: Optional[List[str]]
    matched_skills: Optional[List[str]]
    missing_skills: Optional[List[str]]
    analysis_summary: Optional[str]
    recommendation_level: Optional[str]
    interview_questions: Optional[List[str]]
    recruiter_notes: Optional[str]
    highlight_points: Optional[List[str]]
    red_flags: Optional[List[str]]


class ScoreDistribution(BaseModel):
    range: str
    count: int
    percentage: float


class DashboardResponse(BaseModel):
    job_description_id: uuid.UUID
    job_title: str
    company_name: Optional[str]
    status: str
    total_resumes: int
    processed_resumes: int
    failed_resumes: int
    top_candidates: List[CandidateSummary]
    score_distribution: List[ScoreDistribution]
    avg_overall_score: Optional[float]
    avg_experience_years: Optional[float]
    top_matched_skills: List[Dict[str, Any]]
    processing_completed_at: Optional[datetime]
    created_at: datetime


class PipelineStatusResponse(BaseModel):
    job_description_id: uuid.UUID
    status: str
    total_resumes: int
    parsed: int
    profiled: int
    matched: int
    ranked: int
    recommended: int
    failed: int
    progress_percentage: float
    estimated_completion_seconds: Optional[int]
    error_message: Optional[str]
    # Token optimisation stats
    matching_llm_calls: Optional[int] = None
    matching_llm_skipped: Optional[int] = None
    recommendation_llm_calls: Optional[int] = None
    recommendation_rule_based: Optional[int] = None
    freshers_detected: Optional[int] = None
    experienced_detected: Optional[int] = None
