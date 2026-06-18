from __future__ import annotations
import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class SalaryRange(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: str = "USD"
    period: str = "annual"


class JDAnalysisResult(BaseModel):
    title: str
    company_name: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    experience_level: Optional[str] = None
    min_years_experience: Optional[float] = None
    max_years_experience: Optional[float] = None
    education_requirements: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    company_context: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary_range: Optional[SalaryRange] = None
    industry: Optional[str] = None


class JobDescriptionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)
    description_text: str = Field(..., min_length=10)


class JobDescriptionResponse(BaseModel):
    id: uuid.UUID
    title: str
    company_name: Optional[str]
    description_text: str
    file_path: Optional[str]
    required_skills: Optional[List[str]]
    preferred_skills: Optional[List[str]]
    experience_level: Optional[str]
    min_years_experience: Optional[float]
    max_years_experience: Optional[float]
    education_requirements: Optional[List[str]]
    responsibilities: Optional[List[str]]
    company_context: Optional[str]
    location: Optional[str]
    employment_type: Optional[str]
    salary_range: Optional[dict]
    industry: Optional[str]
    status: str
    is_active: Optional[bool] = True
    error_message: Optional[str]
    total_resumes: Optional[int] = 0
    processed_resumes: Optional[int] = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDescriptionListResponse(BaseModel):
    items: List[JobDescriptionResponse]
    total: int
    page: int
    page_size: int
    pages: int


class JobTitleItem(BaseModel):
    id: uuid.UUID
    title: str
    company_name: Optional[str]

    model_config = {"from_attributes": True}


class JobTitleListResponse(BaseModel):
    items: List[JobTitleItem]
    total: int
    page: int
    page_size: int
    pages: int
