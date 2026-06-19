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


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _list_by_status_global(
    status: Optional[str],
    page: int,
    page_size: int,
    db: AsyncSession,
) -> CandidateStatusListResponse:
    query = select(CandidateProfile)
    if status:
        query = query.where(CandidateProfile.status == CandidateStatus(status))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    profiles = (await db.execute(
        query.order_by(CandidateProfile.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

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

    items = [
        CandidateStatusItem(
            candidate_profile_id=p.id,
            resume_id=p.resume_id,
            full_name=p.full_name,
            email=p.email,
            location=p.location,
            total_years_experience=p.total_years_experience,
            overall_score=mrs[str(p.id)].overall_score if str(p.id) in mrs else None,
            rank=mrs[str(p.id)].rank if str(p.id) in mrs else None,
            status=p.status.value,
        )
        for p in profiles
    ]
    return CandidateStatusListResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=CandidateStatusListResponse)
async def list_all_candidates_by_status(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: pending | accepted | rejected"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all candidate profiles across all JDs, optionally filtered by HR status."""
    if status and status not in ("pending", "accepted", "rejected"):
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Use: pending, accepted, rejected")
    return await _list_by_status_global(status, page, page_size, db)


@router.get("/accepted", response_model=CandidateStatusListResponse)
async def list_accepted_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all accepted candidates across all JDs."""
    return await _list_by_status_global("accepted", page, page_size, db)


@router.get("/rejected", response_model=CandidateStatusListResponse)
async def list_rejected_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all rejected candidates across all JDs."""
    return await _list_by_status_global("rejected", page, page_size, db)


@router.get("/pending", response_model=CandidateStatusListResponse)
async def list_pending_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all pending candidates across all JDs."""
    return await _list_by_status_global("pending", page, page_size, db)


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
