from __future__ import annotations
import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class ResumeResponse(BaseModel):
    id: uuid.UUID
    job_description_id: uuid.UUID
    filename: str
    original_filename: str
    file_size_bytes: Optional[int]
    file_type: Optional[str]
    page_count: Optional[int]
    status: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Candidate profile fields (populated after pipeline runs)
    candidate_profile_id: Optional[uuid.UUID] = None
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None
    candidate_status: Optional[str] = None

    # Match result fields
    overall_score: Optional[float] = None
    skill_match_score: Optional[float] = None
    experience_score: Optional[float] = None
    education_score: Optional[float] = None
    semantic_similarity_score: Optional[float] = None
    rank: Optional[int] = None

    # Recommendation
    recommendation_level: Optional[str] = None

    model_config = {"from_attributes": True}


class ResumeListResponse(BaseModel):
    items: List[ResumeResponse]
    total: int
    page: int
    page_size: int
    pages: int


class BulkUploadResponse(BaseModel):
    job_description_id: uuid.UUID
    total_uploaded: int
    failed_files: List[str] = []
    resume_ids: List[uuid.UUID] = []
    message: str
