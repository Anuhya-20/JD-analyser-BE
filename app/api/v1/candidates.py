"""
Candidate profile status management — Accept / Reject / Pending.
"""
from __future__ import annotations
import math
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from pydantic import BaseModel
from loguru import logger

from app.database import get_db
from app.models.hr_user import HRUser
from app.models.job_description import JobDescription
from app.models.candidate_profile import CandidateProfile, CandidateStatus
from app.models.match_result import MatchResult, MatchStatus
from app.core.deps import get_current_hr_user

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class CandidateStatusUpdate(BaseModel):
    status: CandidateStatus


class CandidateStatusItem(BaseModel):
    candidate_profile_id: uuid.UUID
    resume_id: uuid.UUID
    full_name: Optional[str]
    email: Optional[str]
    location: Optional[str]
    total_years_experience: Optional[float]
    overall_score: Optional[float]
    rank: Optional[int]
    status: str

    model_config = {"from_attributes": True}


class CandidateStatusListResponse(BaseModel):
    items: List[CandidateStatusItem]
    total: int
    page: int
    page_size: int
    pages: int


class AcceptedCandidateItem(BaseModel):
    candidate_profile_id: uuid.UUID
    resume_id: uuid.UUID
    full_name: Optional[str]
    email: Optional[str]
    location: Optional[str]
    total_years_experience: Optional[float]
    overall_score: Optional[float]
    rank: Optional[int]
    jd_id: uuid.UUID
    job_title: Optional[str]
    company_name: Optional[str]
    status: str = "accepted"

    model_config = {"from_attributes": True}


class AcceptedCandidateListResponse(BaseModel):
    items: List[AcceptedCandidateItem]
    total: int
    page: int
    page_size: int
    pages: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/accepted", response_model=AcceptedCandidateListResponse)
async def list_accepted_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by candidate name or email"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Return all accepted candidates across all job descriptions with JD info and match scores."""
    base_q = select(CandidateProfile).where(CandidateProfile.status == CandidateStatus.ACCEPTED)

    if search:
        term = f"%{search.strip()}%"
        base_q = base_q.where(
            (CandidateProfile.full_name.ilike(term)) | (CandidateProfile.email.ilike(term))
        )

    total = (await db.execute(select(func.count()).select_from(base_q.subquery()))).scalar_one()

    profiles = (await db.execute(
        base_q.order_by(CandidateProfile.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    if not profiles:
        return AcceptedCandidateListResponse(items=[], total=0, page=page, page_size=page_size, pages=1)

    profile_ids = [p.id for p in profiles]
    jd_ids = list({p.job_description_id for p in profiles})

    # Bulk load match results
    mr_rows = (await db.execute(
        select(MatchResult).where(
            MatchResult.candidate_profile_id.in_(profile_ids),
            MatchResult.status == MatchStatus.COMPLETED,
        )
    )).scalars().all()
    mrs = {str(mr.candidate_profile_id): mr for mr in mr_rows}

    # Bulk load job descriptions
    jd_rows = (await db.execute(
        select(JobDescription).where(JobDescription.id.in_(jd_ids))
    )).scalars().all()
    jds = {str(jd.id): jd for jd in jd_rows}

    items = []
    for p in profiles:
        mr = mrs.get(str(p.id))
        jd = jds.get(str(p.job_description_id))
        items.append(AcceptedCandidateItem(
            candidate_profile_id=p.id,
            resume_id=p.resume_id,
            full_name=p.full_name,
            email=p.email,
            location=p.location,
            total_years_experience=p.total_years_experience,
            overall_score=mr.overall_score if mr else None,
            rank=mr.rank if mr else None,
            jd_id=p.job_description_id,
            job_title=jd.title if jd else None,
            company_name=jd.company_name if jd else None,
            status="accepted",
        ))

    return AcceptedCandidateListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{jd_id}", response_model=CandidateStatusListResponse)
async def list_candidates_with_status(
    jd_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: pending | accepted | rejected"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all candidate profiles for a JD with their Accept/Reject/Pending status."""
    jd = (await db.execute(select(JobDescription).where(JobDescription.id == jd_id))).scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    query = select(CandidateProfile).where(CandidateProfile.job_description_id == jd_id)

    if status:
        try:
            status_enum = CandidateStatus(status)
            query = query.where(CandidateProfile.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Use: pending, accepted, rejected")

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()

    profiles = (await db.execute(
        query.order_by(CandidateProfile.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    # Bulk load match results for scores/ranks
    profile_ids = [p.id for p in profiles]
    mrs = {}
    if profile_ids:
        mr_rows = (await db.execute(
            select(MatchResult).where(
                MatchResult.candidate_profile_id.in_(profile_ids),
                MatchResult.status == MatchStatus.COMPLETED,
            )
        )).scalars().all()
        mrs = {str(mr.candidate_profile_id): mr for mr in mr_rows}

    items = []
    for p in profiles:
        mr = mrs.get(str(p.id))
        items.append(CandidateStatusItem(
            candidate_profile_id=p.id,
            resume_id=p.resume_id,
            full_name=p.full_name,
            email=p.email,
            location=p.location,
            total_years_experience=p.total_years_experience,
            overall_score=mr.overall_score if mr else None,
            rank=mr.rank if mr else None,
            status=p.status.value,
        ))

    return CandidateStatusListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.patch("/{profile_id}/status", response_model=CandidateStatusItem)
async def update_candidate_status(
    profile_id: uuid.UUID,
    payload: CandidateStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Accept, Reject, or reset to Pending a candidate profile."""
    profile = (await db.execute(
        select(CandidateProfile).where(CandidateProfile.id == profile_id)
    )).scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    await db.execute(
        update(CandidateProfile)
        .where(CandidateProfile.id == profile_id)
        .values(status=payload.status)
    )
    await db.commit()
    await db.refresh(profile)

    mr = (await db.execute(
        select(MatchResult).where(
            MatchResult.candidate_profile_id == profile_id,
            MatchResult.status == MatchStatus.COMPLETED,
        )
    )).scalar_one_or_none()

    logger.info(f"Candidate {profile_id} status → {payload.status.value} by {current_user.email}")

    return CandidateStatusItem(
        candidate_profile_id=profile.id,
        resume_id=profile.resume_id,
        full_name=profile.full_name,
        email=profile.email,
        location=profile.location,
        total_years_experience=profile.total_years_experience,
        overall_score=mr.overall_score if mr else None,
        rank=mr.rank if mr else None,
        status=profile.status.value,
    )
