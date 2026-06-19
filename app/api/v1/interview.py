"""
Interview question generation — tailored questions for accepted candidates.
Generates 5 Technical + 4 Behavioral + 3 Scenario-Based questions using
the JD requirements and candidate's resume profile as context.
Questions are persisted in the interview_sessions table with direct FK
relations to candidate_profile, job_description, match_result, and hr_user.
"""
from __future__ import annotations
import uuid
import asyncio
import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from loguru import logger

from app.database import get_db
from app.models.hr_user import HRUser
from app.models.job_description import JobDescription
from app.models.candidate_profile import CandidateProfile, CandidateStatus
from app.models.match_result import MatchResult, MatchStatus
from app.models.interview_session import InterviewSession
from app.core.deps import get_current_hr_user
from app.agents.llm_factory import get_llm

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class InterviewQuestion(BaseModel):
    question: str
    purpose: str


class InterviewQuestionsResponse(BaseModel):
    id: uuid.UUID
    jd_id: uuid.UUID
    profile_id: uuid.UUID
    match_result_id: Optional[uuid.UUID]
    generated_by_id: Optional[uuid.UUID]
    candidate_name: Optional[str]
    job_title: str
    round_label: Optional[str]
    technical_questions: List[InterviewQuestion]
    behavioral_questions: List[InterviewQuestion]
    scenario_questions: List[InterviewQuestion]
    total_questions: int

    model_config = {"from_attributes": True}


class _LLMQuestions(BaseModel):
    technical_questions: List[InterviewQuestion]
    behavioral_questions: List[InterviewQuestion]
    scenario_questions: List[InterviewQuestion]


# ── Prompt helpers ────────────────────────────────────────────────────────────

def _fmt_list(items: list | None, max_items: int = 12) -> str:
    if not items:
        return "Not specified"
    if isinstance(items[0], dict):
        extracted = []
        for item in items[:max_items]:
            val = item.get("name") or item.get("skill") or item.get("title") or str(item)
            extracted.append(str(val))
        return ", ".join(extracted)
    return ", ".join(str(i) for i in items[:max_items])


def _fmt_work_experience(work_exp: list | None) -> str:
    if not work_exp:
        return "Not provided"
    parts = []
    for w in work_exp[:3]:
        if not isinstance(w, dict):
            continue
        title = w.get("title") or w.get("position") or "Role"
        company = w.get("company") or w.get("organization") or ""
        start = w.get("start_date") or ""
        end = w.get("end_date") or "Present"
        duration = w.get("duration") or f"{start} – {end}"
        responsibilities = w.get("responsibilities") or w.get("description") or ""
        if isinstance(responsibilities, list):
            responsibilities = "; ".join(str(r) for r in responsibilities[:2])
        line = f"{title} at {company} ({duration})"
        if responsibilities:
            line += f": {str(responsibilities)[:120]}"
        parts.append(line)
    return " | ".join(parts) if parts else "Not provided"


def _fmt_education(education: list | None) -> str:
    if not education:
        return "Not provided"
    parts = []
    for e in education[:2]:
        if not isinstance(e, dict):
            continue
        degree = e.get("degree") or e.get("qualification") or "Degree"
        institution = e.get("institution") or e.get("university") or ""
        year = e.get("year") or e.get("graduation_year") or ""
        parts.append(f"{degree} from {institution} {year}".strip())
    return "; ".join(parts) if parts else "Not provided"


def _build_prompt(jd: JobDescription, profile: CandidateProfile) -> str:
    return f"""You are a senior HR interviewer and talent assessor. Generate targeted interview questions for a candidate shortlisted for the role below.

## Job Details
- Title: {jd.title}
- Company: {jd.company_name or 'Not specified'}
- Industry: {jd.industry or 'Not specified'}
- Experience Level: {jd.experience_level or 'Not specified'}
- Required Skills: {_fmt_list(jd.required_skills)}
- Preferred Skills: {_fmt_list(jd.preferred_skills)}
- Key Responsibilities: {_fmt_list(jd.responsibilities)}

## Candidate Profile
- Name: {profile.full_name or 'Candidate'}
- Total Experience: {profile.total_years_experience or 0} years
- Skills: {_fmt_list(profile.skills)}
- Education: {_fmt_education(profile.education)}
- Work History: {_fmt_work_experience(profile.work_experience)}
- Summary: {(profile.summary or 'Not provided')[:300]}

## Instructions
Generate EXACTLY:
1. **5 Technical Questions**: Test depth of knowledge in the required skills. Probe areas where the candidate's skills match the JD requirements and challenge known gaps. Make questions specific, not generic.
2. **4 Behavioral Questions**: Use STAR-format prompts (Situation, Task, Action, Result). Base them on the JD responsibilities and the candidate's actual work history. Focus on leadership, collaboration, problem-solving, and domain-specific behaviors.
3. **3 Scenario-Based Questions**: Present realistic hypothetical situations the candidate would face in this actual role. Test judgment, decision-making, and role-specific problem-solving.

For each question include a concise "purpose" field (1 sentence) explaining what competency or quality it evaluates.

Return ONLY valid JSON with this exact structure — no markdown, no commentary:
{{
  "technical_questions": [
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}}
  ],
  "behavioral_questions": [
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}}
  ],
  "scenario_questions": [
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}},
    {{"question": "...", "purpose": "..."}}
  ]
}}"""


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


async def _call_llm(prompt: str) -> _LLMQuestions:
    llm = get_llm(temperature=0.7, max_tokens=2048)
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, llm.invoke, prompt)
    raw = response.content if hasattr(response, "content") else str(response)
    data = _extract_json(raw)
    return _LLMQuestions(**data)


def _session_to_response(
    session: InterviewSession,
    profile: CandidateProfile,
    jd: JobDescription,
) -> InterviewQuestionsResponse:
    return InterviewQuestionsResponse(
        id=session.id,
        jd_id=session.job_description_id,
        profile_id=session.candidate_profile_id,
        match_result_id=session.match_result_id,
        generated_by_id=session.generated_by_id,
        candidate_name=profile.full_name,
        job_title=jd.title,
        round_label=session.round_label,
        technical_questions=[InterviewQuestion(**q) for q in (session.technical_questions or [])],
        behavioral_questions=[InterviewQuestion(**q) for q in (session.behavioral_questions or [])],
        scenario_questions=[InterviewQuestion(**q) for q in (session.scenario_questions or [])],
        total_questions=session.total_questions,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{jd_id}/{profile_id}", response_model=InterviewQuestionsResponse)
async def generate_interview_questions(
    jd_id: uuid.UUID,
    profile_id: uuid.UUID,
    round_label: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Generate and **persist** tailored interview questions for an accepted candidate.

    - **5 Technical** — skills depth and JD requirements
    - **4 Behavioral** — STAR-format, based on work history
    - **3 Scenario-Based** — hypothetical role-specific situations

    Questions are stored in `interview_sessions` with FK relations to:
    candidate_profile, job_description, match_result, and hr_user.
    Re-calling this endpoint overwrites the previous session for this candidate+JD pair.
    """
    jd = (await db.execute(select(JobDescription).where(JobDescription.id == jd_id))).scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    profile = (await db.execute(
        select(CandidateProfile).where(CandidateProfile.id == profile_id)
    )).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    if profile.status != CandidateStatus.ACCEPTED:
        raise HTTPException(
            status_code=400,
            detail=f"Interview questions can only be generated for accepted candidates. Current status: '{profile.status.value}'",
        )

    if profile.job_description_id != jd_id:
        raise HTTPException(
            status_code=400,
            detail="This candidate profile does not belong to the specified job description",
        )

    # Resolve match_result_id for the FK link
    mr = (await db.execute(
        select(MatchResult).where(
            MatchResult.candidate_profile_id == profile_id,
            MatchResult.status == MatchStatus.COMPLETED,
        )
    )).scalar_one_or_none()

    logger.info(f"Generating interview questions | jd={jd_id} profile={profile_id} user={current_user.email}")

    try:
        questions = await _call_llm(_build_prompt(jd, profile))
    except Exception as exc:
        logger.error(f"LLM error generating interview questions for profile={profile_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to generate interview questions: {exc}")

    total = (
        len(questions.technical_questions)
        + len(questions.behavioral_questions)
        + len(questions.scenario_questions)
    )

    # Upsert: delete existing session for this candidate+JD pair, then insert fresh
    existing = (await db.execute(
        select(InterviewSession).where(
            InterviewSession.candidate_profile_id == profile_id,
            InterviewSession.job_description_id == jd_id,
        )
    )).scalar_one_or_none()

    if existing:
        await db.delete(existing)
        await db.flush()

    session = InterviewSession(
        candidate_profile_id=profile_id,
        job_description_id=jd_id,
        match_result_id=mr.id if mr else None,
        generated_by_id=current_user.id,
        technical_questions=[q.model_dump() for q in questions.technical_questions],
        behavioral_questions=[q.model_dump() for q in questions.behavioral_questions],
        scenario_questions=[q.model_dump() for q in questions.scenario_questions],
        total_questions=total,
        round_label=round_label,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(f"Saved interview session {session.id} | {total} questions | profile={profile_id}")

    return _session_to_response(session, profile, jd)


@router.get("/{jd_id}/{profile_id}", response_model=InterviewQuestionsResponse)
async def get_interview_questions(
    jd_id: uuid.UUID,
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Retrieve previously generated interview questions for a candidate."""
    session = (await db.execute(
        select(InterviewSession).where(
            InterviewSession.candidate_profile_id == profile_id,
            InterviewSession.job_description_id == jd_id,
        )
    )).scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404,
            detail="No interview questions found. Call POST first to generate them.",
        )

    jd = (await db.execute(select(JobDescription).where(JobDescription.id == jd_id))).scalar_one_or_none()
    profile = (await db.execute(
        select(CandidateProfile).where(CandidateProfile.id == profile_id)
    )).scalar_one_or_none()

    return _session_to_response(session, profile, jd)


@router.get("/{jd_id}", response_model=List[InterviewQuestionsResponse])
async def list_interview_sessions_for_jd(
    jd_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all saved interview sessions for a job description."""
    jd = (await db.execute(select(JobDescription).where(JobDescription.id == jd_id))).scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    sessions = (await db.execute(
        select(InterviewSession).where(InterviewSession.job_description_id == jd_id)
    )).scalars().all()

    results = []
    for s in sessions:
        profile = (await db.execute(
            select(CandidateProfile).where(CandidateProfile.id == s.candidate_profile_id)
        )).scalar_one_or_none()
        if profile:
            results.append(_session_to_response(s, profile, jd))
    return results
