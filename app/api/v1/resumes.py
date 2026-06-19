"""
Resume upload and management API endpoints.
"""
from __future__ import annotations
import io
import uuid
import math
import zipfile
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from loguru import logger

from app.config import settings
from app.database import get_db
from app.models.job_description import JobDescription, JDStatus
from app.models.resume import Resume, ResumeStatus
from app.models.candidate_profile import CandidateProfile
from app.models.match_result import MatchResult
from app.models.hr_user import HRUser
from app.core.deps import get_current_hr_user
from app.schemas.resume import ResumeResponse, ResumeListResponse, BulkUploadResponse
from app.services.file_service import file_service
from app.services.pipeline_service import execute_pipeline
from app.utils.pdf_parser import parse_pdf
from app.utils.docx_parser import parse_docx

router = APIRouter()

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
_MAX_FILES_PER_ZIP = 500


def _jd_checks(jd: JobDescription) -> None:
    """Raise 4xx if JD is not in a state that accepts uploads."""
    if not jd:
        raise HTTPException(status_code=404, detail="Job description not found")
    if not jd.is_active:
        raise HTTPException(status_code=403, detail="Job description is inactive")
    if jd.status == JDStatus.ANALYZING:
        raise HTTPException(status_code=409, detail="Pipeline is running — wait for completion")


# ── Individual file upload ─────────────────────────────────────────────────────

@router.post("/{jd_id}/upload", response_model=BulkUploadResponse, status_code=201)
async def upload_resumes(
    jd_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="Resume files (PDF, DOCX, TXT)"),
    auto_process: bool = Query(False, description="Trigger pipeline automatically after upload"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Upload one or more resume files. Set auto_process=true to immediately start the AI pipeline."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    _jd_checks(result.scalar_one_or_none())

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    resume_ids, failed_files = [], []

    for file in files:
        try:
            file_path, unique_filename, file_size, file_type = await file_service.save_resume(file, jd_id)

            # Parse text immediately so raw_text is stored on upload
            raw_text, page_count = "", 0
            try:
                if file_type == "pdf":
                    raw_text, page_count = parse_pdf(file_path)
                elif file_type in ("docx", "doc"):
                    raw_text, page_count = parse_docx(file_path)
                elif file_type == "txt":
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_text = f.read()
                    page_count = 1
            except Exception as parse_err:
                logger.warning(f"[Resume] Text extraction failed for {file.filename}: {parse_err}")

            resume = Resume(
                job_description_id=jd_id,
                filename=unique_filename,
                original_filename=file.filename or unique_filename,
                file_path=file_path,
                file_size_bytes=file_size,
                file_type=file_type,
                raw_text=raw_text or None,
                page_count=page_count or None,
                status=ResumeStatus.PENDING,
            )
            db.add(resume)
            await db.flush()
            resume_ids.append(resume.id)
        except HTTPException:
            failed_files.append(file.filename or "unknown")
        except Exception as e:
            logger.error(f"Failed to save {file.filename}: {e}")
            failed_files.append(file.filename or "unknown")

    await db.commit()

    if auto_process and resume_ids:
        background_tasks.add_task(execute_pipeline, jd_id)

    return BulkUploadResponse(
        job_description_id=jd_id,
        total_uploaded=len(resume_ids),
        failed_files=failed_files,
        resume_ids=resume_ids,
        message=(
            f"Uploaded {len(resume_ids)} resume(s)."
            + (f" {len(failed_files)} failed." if failed_files else "")
            + (" Pipeline started." if auto_process and resume_ids else " Call /process to start the pipeline.")
        ),
    )


# ── ZIP bulk upload ────────────────────────────────────────────────────────────

@router.post("/{jd_id}/upload-zip", response_model=BulkUploadResponse, status_code=201)
async def upload_zip(
    jd_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP archive containing resume files (PDF, DOCX, TXT)"),
    auto_process: bool = Query(False, description="Trigger pipeline automatically after upload"),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """
    Upload a ZIP file containing multiple resumes.
    All PDF, DOCX, and TXT files inside are extracted and queued for processing.
    Nested folders, hidden files, and non-resume files are automatically skipped.
    """
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    jd = result.scalar_one_or_none()
    _jd_checks(jd)

    # Validate it's actually a ZIP
    filename = file.filename or ""
    ct = file.content_type or ""
    if not (filename.lower().endswith(".zip") or "zip" in ct):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive (.zip)")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="ZIP file is empty")

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP file")

    job_dir = Path(settings.UPLOAD_DIR) / "resumes" / str(jd_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    resume_ids, failed_files = [], []
    skipped = 0

    for entry in zf.infolist():
        if len(resume_ids) >= _MAX_FILES_PER_ZIP:
            logger.warning(f"[ZIP] Reached max {_MAX_FILES_PER_ZIP} files — stopping extraction")
            break

        # Skip directories and OS-generated metadata
        if entry.is_dir():
            continue
        basename = Path(entry.filename).name
        if basename.startswith(".") or "__MACOSX" in entry.filename or basename.startswith("~"):
            continue

        ext = Path(basename).suffix.lower()
        if ext not in _ALLOWED_EXTENSIONS:
            skipped += 1
            continue

        try:
            file_data = zf.read(entry.filename)

            if len(file_data) == 0:
                skipped += 1
                continue
            if len(file_data) > max_bytes:
                failed_files.append(f"{basename} (too large)")
                continue

            file_type = ext.lstrip(".")
            unique_filename = f"{uuid.uuid4()}{ext}"
            dest = job_dir / unique_filename
            dest.write_bytes(file_data)

            # Parse text immediately
            raw_text, page_count = "", 0
            try:
                if file_type == "pdf":
                    raw_text, page_count = parse_pdf(str(dest))
                elif file_type in ("docx", "doc"):
                    raw_text, page_count = parse_docx(str(dest))
                elif file_type == "txt":
                    raw_text = dest.read_text(encoding="utf-8", errors="ignore")
                    page_count = 1
            except Exception as parse_err:
                logger.warning(f"[ZIP] Text extraction failed for {basename}: {parse_err}")

            resume = Resume(
                job_description_id=jd_id,
                filename=unique_filename,
                original_filename=basename,
                file_path=str(dest),
                file_size_bytes=len(file_data),
                file_type=file_type,
                raw_text=raw_text or None,
                page_count=page_count or None,
                status=ResumeStatus.PENDING,
            )
            db.add(resume)
            await db.flush()
            resume_ids.append(resume.id)
            logger.debug(f"[ZIP] Extracted {basename} → {unique_filename}")

        except Exception as e:
            logger.error(f"[ZIP] Failed to extract {basename}: {e}")
            failed_files.append(basename)

    zf.close()
    await db.commit()

    if auto_process and resume_ids:
        background_tasks.add_task(execute_pipeline, jd_id)

    skipped_msg = f" {skipped} non-resume files ignored." if skipped else ""
    failed_msg = f" {len(failed_files)} failed." if failed_files else ""
    auto_msg = " Pipeline started." if auto_process and resume_ids else " Call /process to start the pipeline."

    return BulkUploadResponse(
        job_description_id=jd_id,
        total_uploaded=len(resume_ids),
        failed_files=failed_files,
        resume_ids=resume_ids,
        message=f"Extracted {len(resume_ids)} resumes from ZIP.{skipped_msg}{failed_msg}{auto_msg}",
    )


# ── List / get / delete ────────────────────────────────────────────────────────

@router.get("/{jd_id}", response_model=ResumeListResponse)
async def list_resumes(
    jd_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """List all resumes uploaded for a job description, enriched with candidate and match data."""
    result = await db.execute(select(JobDescription).where(JobDescription.id == jd_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job description not found")

    base_query = select(Resume).where(Resume.job_description_id == jd_id)
    if status:
        try:
            base_query = base_query.where(Resume.status == ResumeStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    # Single query: resumes + candidate profile + match result (LEFT JOINs)
    enriched_query = (
        select(
            Resume,
            CandidateProfile.id.label("cp_id"),
            CandidateProfile.full_name,
            CandidateProfile.email,
            CandidateProfile.status.label("cp_status"),
            MatchResult.overall_score,
            MatchResult.rank,
        )
        .where(Resume.job_description_id == jd_id)
        .outerjoin(CandidateProfile, CandidateProfile.resume_id == Resume.id)
        .outerjoin(MatchResult, MatchResult.candidate_profile_id == CandidateProfile.id)
        .order_by(
            MatchResult.rank.asc().nulls_last(),
            Resume.created_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if status:
        try:
            enriched_query = enriched_query.where(Resume.status == ResumeStatus(status))
        except ValueError:
            pass

    rows = (await db.execute(enriched_query)).all()

    items = []
    for row in rows:
        resume = row[0]
        data = ResumeResponse.model_validate(resume)
        data.candidate_profile_id = row[1]
        data.candidate_name = row[2]
        data.candidate_email = row[3]
        data.candidate_status = row[4].value if row[4] else None
        data.overall_score = row[5]
        data.rank = row[6]
        items.append(data)

    return ResumeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/single/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Get a single resume record by ID."""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return ResumeResponse.model_validate(resume)


@router.delete("/single/{resume_id}", status_code=204)
async def delete_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: HRUser = Depends(get_current_hr_user),
):
    """Delete a single resume (only if not currently being processed)."""
    result = await db.execute(select(Resume).where(Resume.id == resume_id))
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    if resume.status in (ResumeStatus.PARSING, ResumeStatus.PROFILING):
        raise HTTPException(status_code=409, detail="Cannot delete resume while processing")

    file_service.delete_file(resume.file_path)
    await db.delete(resume)
    await db.commit()
