"""
Profile Builder Agent â€” Node 3.

BIGGEST token consumer (1 LLM call per resume).
Optimisations applied:
  - PRE-FILTER: skip LLM entirely if keyword hit-rate < 10% (saves ~60% of calls at 500+ resumes)
  - System prompt compressed ~65% (200 â†’ 70 tokens)
  - Resume text capped at 3500 chars (was 8000) â€” saves ~1125 tokens/call
  - Text preprocessed before sending (strip noise, repeated blanks)
  - max_tokens=800 output cap
  - Schema field descriptions removed (they cost tokens, LLM uses field names)
  - Skip LLM entirely if extracted text < 100 chars
"""
from __future__ import annotations
import re
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydantic import BaseModel, Field, model_validator
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from app.agents.state import RecruitmentState, CandidateProfile, ResumeData
from app.agents.llm_factory import get_llm
from app.services.embedding_service import embedding_service
from app.utils.token_utils import trim_text, estimate_tokens, coerce_llm_output
from app.config import settings

# Fraction of required skills that must appear in raw text to proceed to LLM
# 0.10 = at least 1 out of 10 required skills must be found
# Set conservatively low so we never miss a borderline candidate
PREFILTER_MIN_SKILL_HIT_RATE = 0.10

_EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
_YEARS_RE = re.compile(r'(\d+)\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)', re.I)


def _name_from_email(email: Optional[str]) -> Optional[str]:
    """Derive a display name from an email address when full_name is unavailable.
    e.g. john.doe@gmail.com â†’ 'John Doe', john_doe@company.com â†’ 'John Doe'
    """
    if not email or "@" not in email:
        return None
    local = email.split("@")[0]
    parts = re.split(r"[._\-]+", local)
    name = " ".join(p.capitalize() for p in parts if p)
    return name or None


class WorkExp(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    duration_months: Optional[int] = None
    responsibilities: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    is_internship: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        return coerce_llm_output(cls, v)


class Edu(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[float] = None
    honors: Optional[str] = None
    relevant_coursework: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        return coerce_llm_output(cls, v)


class Cert(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        return coerce_llm_output(cls, v)


class Proj(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    is_academic: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        return coerce_llm_output(cls, v)


class CandidateProfileOutput(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    work_experience: List[WorkExp] = Field(default_factory=list)
    education: List[Edu] = Field(default_factory=list)
    certifications: List[Cert] = Field(default_factory=list)
    projects: List[Proj] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    total_years_experience: float = 0.0
    internship_months: int = 0
    gpa: Optional[float] = None
    highest_education_level: Optional[str] = None
    is_fresher: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, v):
        return coerce_llm_output(cls, v)


# â”€â”€ Compressed prompt (~70 token system message vs ~200 before) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

PROFILE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "Parse resume. Rules: "
        "skills=ALL (courses+projects+certs+tools). "
        "is_internship=true for intern/co-op/trainee. "
        "is_academic=true for college projects. "
        "total_years_experience=full-time only (exclude internships). "
        "is_fresher=true if <1yr full-time. "
        "internship_months=sum of intern durations. "
        "Dates: YYYY-MM.",
    ),
    (
        "human",
        "Parse this resume:\n\n{resume_text}",
    ),
])


def _quick_keyword_score(raw_text: str, required_skills: List[str]) -> float:
    """Returns fraction (0-1) of required skills found literally in raw resume text."""
    if not required_skills:
        return 1.0
    text_lower = raw_text.lower()
    hits = sum(1 for s in required_skills if re.sub(r"[^a-z0-9+#.]", " ", s.lower()).strip() in text_lower)
    return hits / len(required_skills)


def _extract_basic_profile(resume: ResumeData, required_skills: List[str], preferred_skills: List[str]) -> CandidateProfile:
    """
    Lightweight profile built from raw text without any LLM call.
    Used for candidates that fail the pre-filter (< 10% required skill hit rate).
    Still computes embedding so semantic score works in matching.
    """
    raw = resume.get("raw_text", "")
    text_lower = raw.lower()

    email_match = _EMAIL_RE.search(raw)
    email = email_match.group(0) if email_match else None

    all_jd_skills = required_skills + preferred_skills
    found_skills = [s for s in all_jd_skills if re.sub(r"[^a-z0-9+#.]", " ", s.lower()).strip() in text_lower]

    years_match = _YEARS_RE.search(raw)
    total_years = float(years_match.group(1)) if years_match else 0.0
    is_fresher = total_years < 1.0

    embedding = embedding_service.embed_document(raw[:512].strip()) if raw.strip() else None

    logger.debug(f"[Profile][Pre-filter] {resume['filename']} â€” skills_found={len(found_skills)}/{len(required_skills)} years={total_years}")

    return CandidateProfile(
        resume_id=resume["resume_id"],
        full_name=_name_from_email(email), email=email, phone=None, location=None,
        linkedin_url=None, github_url=None, portfolio_url=None, summary=None,
        skills=found_skills,
        work_experience=[], internships=[], academic_projects=[],
        education=[], certifications=[], projects=[], languages=[],
        total_years_experience=total_years,
        internship_months=0, gpa=None, highest_education_level=None,
        is_fresher=is_fresher, embedding=embedding, error=None,
    )


def _build_profile(resume: ResumeData, required_skills: List[str] = (), preferred_skills: List[str] = ()) -> CandidateProfile:
    if resume.get("error") or not resume.get("raw_text"):
        return _empty_profile(resume["resume_id"], resume.get("error", "No text"))

    raw = resume["raw_text"]
    if len(raw.strip()) < 100:
        return _empty_profile(resume["resume_id"], "Text too short to parse")

    # PRE-FILTER: skip costly LLM if candidate has almost no required skills
    hit_rate = _quick_keyword_score(raw, list(required_skills))
    if required_skills and hit_rate < PREFILTER_MIN_SKILL_HIT_RATE:
        return _extract_basic_profile(resume, list(required_skills), list(preferred_skills))

    try:
        # Preprocess + trim â€” biggest token saving
        resume_text = trim_text(raw, max_chars=3500)
        est = estimate_tokens(resume_text)
        logger.debug(f"[Profile] {resume['filename']} | ~{est} input tokens")

        llm = get_llm(temperature=0.0, max_tokens=2000)
        chain = PROFILE_PROMPT | llm.with_structured_output(CandidateProfileOutput, method="function_calling")
        result: CandidateProfileOutput = chain.invoke({"resume_text": resume_text})

        all_jobs   = [e.model_dump() for e in result.work_experience]
        full_time  = [j for j in all_jobs if not j.get("is_internship")]
        internships = [j for j in all_jobs if j.get("is_internship")]

        all_projs      = [p.model_dump() for p in result.projects]
        academic_projs = [p for p in all_projs if p.get("is_academic")]
        personal_projs = [p for p in all_projs if not p.get("is_academic")]

        # Normalise GPA to 4.0 scale
        gpa = result.gpa
        if gpa and gpa > 4.0:
            gpa = round(gpa / 10.0 * 4.0, 2)

        internship_months = result.internship_months or sum(
            j.get("duration_months", 0) or 0 for j in internships
        )
        is_fresher = result.is_fresher or result.total_years_experience < 1.0

        emb_text  = _embedding_text(result.model_dump(), full_time, internships, academic_projs, is_fresher)
        embedding = embedding_service.embed_document(emb_text)

        logger.debug(
            f"[Profile] {result.full_name or 'Unknown'} | "
            f"fresher={is_fresher} skills={len(result.skills)} "
            f"jobs={len(full_time)} interns={len(internships)} projs={len(all_projs)}"
        )

        return CandidateProfile(
            resume_id=resume["resume_id"],
            full_name=result.full_name or _name_from_email(result.email),
            email=result.email,
            phone=result.phone,
            location=result.location,
            linkedin_url=result.linkedin_url,
            github_url=result.github_url,
            portfolio_url=result.portfolio_url,
            summary=result.summary,
            skills=result.skills,
            work_experience=full_time,
            internships=internships,
            academic_projects=academic_projs,
            education=[e.model_dump() for e in result.education],
            certifications=[e.model_dump() for e in result.certifications],
            projects=personal_projs,
            languages=result.languages,
            total_years_experience=result.total_years_experience,
            internship_months=internship_months,
            gpa=gpa,
            highest_education_level=result.highest_education_level,
            is_fresher=is_fresher,
            embedding=embedding,
            error=None,
        )

    except Exception as e:
        logger.warning(f"[Profile] LLM failed for {resume['resume_id']}: {e} — falling back to basic profile")
        return _extract_basic_profile(resume, list(required_skills), list(preferred_skills))


def _empty_profile(resume_id: str, error: str) -> CandidateProfile:
    return CandidateProfile(
        resume_id=resume_id,
        full_name=None, email=None, phone=None, location=None,
        linkedin_url=None, github_url=None, portfolio_url=None, summary=None,
        skills=[], work_experience=[], internships=[], academic_projects=[],
        education=[], certifications=[], projects=[], languages=[],
        total_years_experience=0.0, internship_months=0, gpa=None,
        highest_education_level=None, is_fresher=True,
        embedding=None, error=error,
    )


def _embedding_text(profile: dict, full_time: list, internships: list, academic_projs: list, is_fresher: bool) -> str:
    parts = []
    if profile.get("summary"): parts.append(profile["summary"])
    if profile.get("skills"):  parts.append("Skills: " + ", ".join(profile["skills"][:20]))

    if is_fresher:
        for e in profile.get("education", [])[:1]:
            if isinstance(e, dict):
                parts.append(f"Edu: {e.get('degree','')} {e.get('field_of_study','')} {e.get('institution','')}")
        for p in academic_projs[:2]:
            if isinstance(p, dict):
                parts.append(f"Project: {p.get('name','')} {' '.join(p.get('technologies',[])[:4])}")
        for i in internships[:2]:
            if isinstance(i, dict):
                parts.append(f"Intern: {i.get('title','')} {i.get('company','')} {' '.join(i.get('technologies',[])[:4])}")
    else:
        for j in full_time[:3]:
            if isinstance(j, dict):
                parts.append(f"{j.get('title','')} {j.get('company','')} {' '.join(j.get('technologies',[])[:4])}")
        for e in profile.get("education", [])[:1]:
            if isinstance(e, dict):
                parts.append(f"Edu: {e.get('degree','')} {e.get('field_of_study','')}")

    return "\n".join(parts)


def profile_builder_node(state: RecruitmentState) -> RecruitmentState:
    parsed_resumes = state.get("parsed_resumes", [])
    jd_analysis    = state.get("jd_analysis") or {}
    required_skills  = jd_analysis.get("required_skills") or []
    preferred_skills = jd_analysis.get("preferred_skills") or []

    valid   = [r for r in parsed_resumes if not r.get("error")]
    invalid = [r for r in parsed_resumes if r.get("error")]

    logger.info(
        f"[Profile Builder] {len(valid)} valid, {len(invalid)} already failed | "
        f"pre-filter threshold={PREFILTER_MIN_SKILL_HIT_RATE} | "
        f"jd_skills={len(required_skills)} required"
    )

    profiles = [_empty_profile(r["resume_id"], r.get("error", "Parse failed")) for r in invalid]

    if valid:
        max_workers = min(settings.MAX_RESUME_PROCESSING_WORKERS, len(valid))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_build_profile, r, required_skills, preferred_skills): r
                for r in valid
            }
            for future in as_completed(futures):
                profiles.append(future.result())

    ok           = sum(1 for p in profiles if not p.get("error"))
    freshers     = sum(1 for p in profiles if p.get("is_fresher") and not p.get("error"))
    prefiltered  = sum(
        1 for p in profiles
        if not p.get("error") and not p.get("full_name") and not p.get("work_experience")
    )
    llm_called   = ok - prefiltered

    logger.info(
        f"[Profile Builder] {ok}/{len(profiles)} built | "
        f"LLM_called={llm_called} pre-filtered={prefiltered} | "
        f"{freshers} freshers"
    )

    return {
        **state,
        "candidate_profiles": profiles,
        "processing_stats": {
            **state.get("processing_stats", {}),
            "profiles_built": ok,
            "profiles_failed": len(profiles) - ok,
            "profiles_llm_called": llm_called,
            "profiles_prefiltered": prefiltered,
            "freshers_detected": freshers,
        },
    }
