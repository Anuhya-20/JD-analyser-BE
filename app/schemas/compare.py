"""
Schemas for candidate comparison endpoint.
"""
from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class CandidateScores(BaseModel):
    overall_score: float
    skill_match_score: Optional[float] = None
    experience_score: Optional[float] = None
    education_score: Optional[float] = None
    semantic_similarity_score: Optional[float] = None


class CandidateCompareItem(BaseModel):
    candidate_profile_id: uuid.UUID
    resume_id: uuid.UUID
    full_name: Optional[str] = None
    email: Optional[str] = None
    location: Optional[str] = None
    total_years_experience: Optional[float] = None
    highest_education_level: Optional[str] = None
    rank: Optional[int] = None

    scores: CandidateScores

    matched_skills: List[str] = []
    missing_skills: List[str] = []
    unique_skills: List[str] = []

    strengths: List[str] = []
    weaknesses: List[str] = []
    analysis_summary: Optional[str] = None
    recommendation_level: Optional[str] = None
    interview_questions: Optional[List[str]] = None
    red_flags: Optional[List[str]] = None
    highlight_points: Optional[List[str]] = None

    wins_on: List[str] = []


class ComparisonInsights(BaseModel):
    best_overall: Optional[str] = None
    best_skill_match: Optional[str] = None
    most_experienced: Optional[str] = None
    common_matched_skills: List[str] = []
    missing_from_all: List[str] = []


class CompareResponse(BaseModel):
    job_description_id: uuid.UUID
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    candidates: List[CandidateCompareItem]
    insights: ComparisonInsights
