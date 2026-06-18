from __future__ import annotations
import uuid
from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel


class WorkExperience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    duration_months: Optional[int] = None
    responsibilities: List[str] = []
    technologies: List[str] = []
    location: Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[float] = None
    honors: Optional[str] = None


class Certification(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_id: Optional[str] = None


class Project(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = []
    url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CandidateProfileResponse(BaseModel):
    id: uuid.UUID
    resume_id: uuid.UUID
    job_description_id: uuid.UUID
    full_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    linkedin_url: Optional[str]
    github_url: Optional[str]
    portfolio_url: Optional[str]
    summary: Optional[str]
    skills: Optional[List[str]]
    work_experience: Optional[List[Dict[str, Any]]]
    education: Optional[List[Dict[str, Any]]]
    certifications: Optional[List[Dict[str, Any]]]
    projects: Optional[List[Dict[str, Any]]]
    languages: Optional[List[str]]
    total_years_experience: Optional[float]
    highest_education_level: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
