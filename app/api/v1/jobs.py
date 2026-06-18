"""
Job Description API endpoints.
"""
from __future__ import annotations
import uuid
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, case, literal_column
from loguru import logger

from app.database import get_db
from app.models.job_description import JobDescription, JDStatus
from app.models.resume import Resume, ResumeStatus
from app.models.hr_user import HRUser
from app.core.deps import get_current_hr_user
from app.schemas.job_description import (
    JobDescriptionCreate,
    JobDescriptionResponse,
    JobDescriptionListResponse,
)
from app.services.file_service import file_service
from app.services.pipeline_service import execute_pipeline, analyze_jd_only
from app.utils.pdf_parser import parse_pdf
from app.utils.docx_parser import parse_docx

router = APIRouter()


async def _extract_text_from_file(file_path: str, file_type: str) -> str:
    if file_type == "pdf":
        text, _ = parse_pdf(file_path)
    elif file_type in ("docx", "doc"):
        text, _ = parse_docx(file_path)
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    return text


@router.post("", response_model=JobDescriptionResponse, status_code=201)
async def create_job_description(
    background_tasks: BackgroundTasks,
    title: str = Form(..., description="Job title"),
    company_name: Optional[str] = Form(None),
    description_text: Optional[str] = Form(None, description="Raw JD text (if not uploading a file)"),
    file: Optional[UploadFile] = File(None, description="JD file (PDF/DOCX/TXT)"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Create a new Job Description. Provide either raw text or a file upload.
    """
    if not description_text and not file:
        raise HTTPException(status_code=400, detail="Provide either description_text or a file")

    file_path = None
    if file:
        try:
            saved_path, _, _, file_type = await file_service.save_jd_file(file)
            file_path = saved_path
            extracted_text = await _extract_text_from_file(saved_path, file_type)
            description_text = extracted_text if not description_text else description_text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process JD file: {str(e)}")

    if not description_text or len(description_text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Job description text is too short")

    jd = JobDescription(
        title=title,
        company_name=company_name,
        description_text=description_text.strip(),
        file_path=file_path,
        status=JDStatus.PENDING,
    )
    db.add(jd)
    await db.commit()
    await db.refresh(jd)

    logger.info(f"Created JD: {jd.id} — {jd.title!r}")

    # Auto-analyze JD in background so structured fields populate immediately
    background_tasks.add_task(analyze_jd_only, jd.id)

    result = _jd_to_response(jd, total_resumes=0, processed_resumes=0)
    return result


@router.get("", response_model=JobDescriptionListResponse)
async def list_job_descriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    active_only: bool = Query(True, description="When true (default), return only active JDs"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List job descriptions. By default returns only active JDs (is_active=true)."""
    query = select(JobDescription)
    if active_only:
        query = query.where(JobDescription.is_active == True)  # noqa: E712
    if status:
        try:
            status_enum = JDStatus(status)
            query = query.where(JobDescription.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    # Build resume counts as correlated subqueries — one DB round-trip instead of 2N
    total_sq = (
        select(func.count(Resume.id))
        .where(Resume.job_description_id == JobDescription.id)
        .scalar_subquery()
    )
    processed_sq = (
        select(func.count(Resume.id))
        .where(
            Resume.job_description_id == JobDescription.id,
            Resume.status == ResumeStatus.COMPLETED,
        )
        .scalar_subquery()
    )

    paged_query = (
        query
        .add_columns(total_sq.label("total_resumes"), processed_sq.label("processed_resumes"))
        .order_by(JobDescription.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(paged_query)
    rows = result.all()

    items = []
    for row in rows:
        jd = row[0]
        total_resumes = row[1] or 0
        processed = row[2] or 0
        items.append(_jd_to_response(jd, total_resumes, processed))

    return JobDescriptionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{jd_id}", response_model=JobDescriptionResponse)
async def get_job_description(jd_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: HRUser = Depends(get_current_hr_user)):
    """Get a single job description by ID."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    counts = await db.execute(
        select(
            func.count(Resume.id).label("total"),
            func.count(
                case((Resume.status == ResumeStatus.COMPLETED, Resume.id))
            ).label("processed"),
        ).where(Resume.job_description_id == jd_id)
    )
    row = counts.one()
    return _jd_to_response(jd, row.total or 0, row.processed or 0)


@router.post("/{jd_id}/process", status_code=202)
async def trigger_pipeline(
    jd_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Trigger the AI recruitment pipeline for an existing JD.
    Returns 202 Accepted — processing happens in the background.
    """
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")

    if jd.status == JDStatus.ANALYZING:
        raise HTTPException(status_code=409, detail="Pipeline is already running for this JD")

    # Check there are resumes to process
    count_result = await db.execute(
        select(func.count()).where(
            Resume.job_description_id == jd_id, Resume.status == ResumeStatus.PENDING
        )
    )
    pending_count = count_result.scalar_one()
    if pending_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No pending resumes found. Upload resumes first.",
        )

    background_tasks.add_task(execute_pipeline, jd_id)

    logger.info(f"[API] Pipeline triggered for JD={jd_id} with {pending_count} pending resumes")
    return {
        "message": "Pipeline started",
        "job_description_id": str(jd_id),
        "pending_resumes": pending_count,
    }


@router.patch("/{jd_id}/activate", response_model=JobDescriptionResponse)
async def activate_job_description(jd_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: HRUser = Depends(get_current_hr_user)):
    """Mark a job description as active — HR can post resumes against it."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    await db.execute(
        update(JobDescription).where(JobDescription.id == jd_id).values(is_active=True)
    )
    await db.commit()
    await db.refresh(jd)
    logger.info(f"Activated JD: {jd_id}")
    counts = await db.execute(
        select(func.count(Resume.id), func.count(case((Resume.status == ResumeStatus.COMPLETED, Resume.id))))
        .where(Resume.job_description_id == jd_id)
    )
    total, processed = counts.one()
    return _jd_to_response(jd, total or 0, processed or 0)


@router.patch("/{jd_id}/deactivate", response_model=JobDescriptionResponse)
async def deactivate_job_description(jd_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: HRUser = Depends(get_current_hr_user)):
    """Mark a job description as inactive — closes it for new resume submissions."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    if jd.status == JDStatus.ANALYZING:
        raise HTTPException(status_code=409, detail="Cannot deactivate while pipeline is running")
    await db.execute(
        update(JobDescription).where(JobDescription.id == jd_id).values(is_active=False)
    )
    await db.commit()
    await db.refresh(jd)
    logger.info(f"Deactivated JD: {jd_id}")
    counts = await db.execute(
        select(func.count(Resume.id), func.count(case((Resume.status == ResumeStatus.COMPLETED, Resume.id))))
        .where(Resume.job_description_id == jd_id)
    )
    total, processed = counts.one()
    return _jd_to_response(jd, total or 0, processed or 0)


def _jd_to_response(jd: JobDescription, total_resumes: int, processed_resumes: int) -> JobDescriptionResponse:
    return JobDescriptionResponse(
        id=jd.id,
        title=jd.title,
        company_name=jd.company_name,
        description_text=jd.description_text,
        file_path=jd.file_path,
        required_skills=jd.required_skills,
        preferred_skills=jd.preferred_skills,
        experience_level=jd.experience_level,
        min_years_experience=jd.min_years_experience,
        max_years_experience=jd.max_years_experience,
        education_requirements=jd.education_requirements,
        responsibilities=jd.responsibilities,
        company_context=jd.company_context,
        location=jd.location,
        employment_type=jd.employment_type,
        salary_range=jd.salary_range,
        industry=jd.industry,
        status=jd.status.value,
        is_active=jd.is_active if jd.is_active is not None else True,
        error_message=jd.error_message,
        total_resumes=total_resumes,
        processed_resumes=processed_resumes,
        created_at=jd.created_at,
        updated_at=jd.updated_at,
    )
