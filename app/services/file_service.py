import uuid
import os
from pathlib import Path
from typing import Tuple
from fastapi import UploadFile, HTTPException
from loguru import logger
from app.config import settings


ALLOWED_RESUME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
}

ALLOWED_JD_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}


class FileService:
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.jd_dir = self.upload_dir / "jds"
        self.resume_dir = self.upload_dir / "resumes"
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.jd_dir.mkdir(parents=True, exist_ok=True)
        self.resume_dir.mkdir(parents=True, exist_ok=True)

    def _check_file_size(self, file: UploadFile):
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        # FastAPI doesn't eagerly read size; we'll check after saving

    def get_file_type(self, content_type: str, filename: str) -> str:
        """Determine file type from content-type or extension."""
        if content_type in ALLOWED_RESUME_TYPES:
            return ALLOWED_RESUME_TYPES[content_type]
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext in ("pdf", "docx", "doc", "txt"):
            return ext
        return "unknown"

    async def save_resume(
        self, file: UploadFile, job_description_id: uuid.UUID
    ) -> Tuple[str, str, int, str]:
        """
        Save an uploaded resume file to disk.
        Returns (file_path, unique_filename, file_size_bytes, file_type).
        """
        file_type = self.get_file_type(file.content_type or "", file.filename or "")
        if file_type not in ("pdf", "docx", "doc", "txt"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Accepted: PDF, DOCX, TXT",
            )

        job_dir = self.resume_dir / str(job_description_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        unique_filename = f"{uuid.uuid4()}.{file_type}"
        file_path = job_dir / unique_filename

        content = await file.read()
        file_size = len(content)

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file_size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size: {settings.MAX_FILE_SIZE_MB}MB",
            )

        with open(file_path, "wb") as f:
            f.write(content)

        logger.debug(f"Saved resume: {file_path} ({file_size} bytes)")
        return str(file_path), unique_filename, file_size, file_type

    async def save_jd_file(self, file: UploadFile) -> Tuple[str, str, int, str]:
        """Save an uploaded JD file to disk."""
        file_type = self.get_file_type(file.content_type or "", file.filename or "")
        if file_type not in ("pdf", "docx", "txt"):
            raise HTTPException(
                status_code=400,
                detail="Unsupported JD file type. Accepted: PDF, DOCX, TXT",
            )

        unique_filename = f"{uuid.uuid4()}.{file_type}"
        file_path = self.jd_dir / unique_filename

        content = await file.read()
        file_size = len(content)

        with open(file_path, "wb") as f:
            f.write(content)

        return str(file_path), unique_filename, file_size, file_type

    def delete_file(self, file_path: str):
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")


file_service = FileService()
