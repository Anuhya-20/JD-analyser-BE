from __future__ import annotations
import uuid
from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel


class MatchResultResponse(BaseModel):
    id: uuid.UUID
    job_description_id: uuid.UUID
    candidate_profile_id: uuid.UUID
    overall_score: Optional[float]
    skill_match_score: Optional[float]
    experience_score: Optional[float]
    education_score: Optional[float]
    semantic_similarity_score: Optional[float]
    keyword_match_score: Optional[float]
    strengths: Optional[List[str]]
    weaknesses: Optional[List[str]]
    matched_skills: Optional[List[str]]
    missing_skills: Optional[List[str]]
    analysis_summary: Optional[str]
    rank: Optional[int]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecommendationResponse(BaseModel):
    id: uuid.UUID
    match_result_id: uuid.UUID
    level: str
    recruiter_notes: Optional[str]
    interview_questions: Optional[List[str]]
    suggested_interview_stages: Optional[List[str]]
    red_flags: Optional[List[str]]
    highlight_points: Optional[List[str]]
    culture_fit_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RankedCandidateResponse(BaseModel):
    rank: int
    overall_score: float
    candidate_profile: Dict[str, Any]
    match_result: Dict[str, Any]
    recommendation: Optional[Dict[str, Any]] = None
