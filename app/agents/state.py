"""
Shared state object that flows through every LangGraph node.
All agents read from and write to this TypedDict.
"""
from __future__ import annotations
from typing import TypedDict, Optional, List, Dict, Any


class ResumeData(TypedDict):
    resume_id: str
    filename: str
    file_path: str
    file_type: str
    raw_text: str
    page_count: int
    error: Optional[str]


class CandidateProfile(TypedDict):
    resume_id: str
    full_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    linkedin_url: Optional[str]
    github_url: Optional[str]
    portfolio_url: Optional[str]
    summary: Optional[str]
    skills: List[str]
    work_experience: List[Dict[str, Any]]      # full-time jobs only
    internships: List[Dict[str, Any]]          # internship records
    academic_projects: List[Dict[str, Any]]    # final year / side projects
    education: List[Dict[str, Any]]
    certifications: List[Dict[str, Any]]
    projects: List[Dict[str, Any]]             # personal/open-source projects
    languages: List[str]
    total_years_experience: float              # professional (non-intern) years
    internship_months: int                     # total internship duration in months
    gpa: Optional[float]                       # latest GPA if present
    highest_education_level: Optional[str]
    is_fresher: bool                           # True when < 1 year full-time exp
    embedding: Optional[List[float]]
    error: Optional[str]


class MatchScore(TypedDict):
    resume_id: str
    overall_score: float
    skill_match_score: float
    experience_score: float
    education_score: float
    semantic_similarity_score: float
    keyword_match_score: float
    matched_skills: List[str]
    missing_skills: List[str]
    strengths: List[str]
    weaknesses: List[str]
    analysis_summary: str
    candidate_tier: str                        # "fresher" | "experienced"
    rank: Optional[int]


class CandidateRecommendation(TypedDict):
    resume_id: str
    recommendation_level: str
    recruiter_notes: str
    interview_questions: List[str]
    suggested_interview_stages: List[str]
    red_flags: List[str]
    highlight_points: List[str]
    culture_fit_notes: str


class RecruitmentState(TypedDict):
    # Input
    job_description_id: str
    job_description_text: str

    # JD Analysis Agent output
    jd_analysis: Optional[Dict[str, Any]]      # includes is_entry_level, accepts_freshers
    jd_embedding: Optional[List[float]]

    # Resume Parser Agent input/output
    resume_file_infos: List[Dict[str, Any]]
    parsed_resumes: List[ResumeData]

    # Profile Builder Agent output
    candidate_profiles: List[CandidateProfile]

    # Matching Agent output
    match_scores: List[MatchScore]

    # Ranking Agent output
    ranked_candidates: List[MatchScore]

    # Recommendation Agent output
    recommendations: List[CandidateRecommendation]

    # Metadata
    errors: List[str]
    processing_stats: Dict[str, Any]
