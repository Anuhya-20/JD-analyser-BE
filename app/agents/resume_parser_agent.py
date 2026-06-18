"""
Resume Parser Agent — Node 2 in the LangGraph workflow.

Reads each resume file from disk and extracts raw text using
pdfplumber / pymupdf (for PDFs) or python-docx (for DOCX).
Runs parsing in a thread pool to handle large batches efficiently.
"""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
from loguru import logger

from app.agents.state import RecruitmentState, ResumeData
from app.config import settings


def _parse_single_resume(info: dict) -> ResumeData:
    """Parse one resume file. Runs in a thread."""
    resume_id = info["resume_id"]
    file_path = info["file_path"]
    filename = info["filename"]
    file_type = info.get("file_type", "pdf")

    try:
        if file_type in ("pdf",):
            from app.utils.pdf_parser import parse_pdf
            raw_text, page_count = parse_pdf(file_path)
        elif file_type in ("docx", "doc"):
            from app.utils.docx_parser import parse_docx
            raw_text, page_count = parse_docx(file_path)
        elif file_type == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_text = f.read()
            page_count = max(1, len(raw_text.split()) // 300)
        else:
            return ResumeData(
                resume_id=resume_id,
                filename=filename,
                file_path=file_path,
                file_type=file_type,
                raw_text="",
                page_count=0,
                error=f"Unsupported file type: {file_type}",
            )

        if not raw_text or len(raw_text.strip()) < 50:
            return ResumeData(
                resume_id=resume_id,
                filename=filename,
                file_path=file_path,
                file_type=file_type,
                raw_text=raw_text or "",
                page_count=page_count,
                error="Extracted text too short — possibly a scanned image or corrupted file",
            )

        logger.debug(f"[Resume Parser] Parsed {filename}: {len(raw_text)} chars, {page_count} pages")
        return ResumeData(
            resume_id=resume_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            raw_text=raw_text,
            page_count=page_count,
            error=None,
        )

    except Exception as e:
        logger.warning(f"[Resume Parser] Failed to parse {filename}: {e}")
        return ResumeData(
            resume_id=resume_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            raw_text="",
            page_count=0,
            error=str(e),
        )


def resume_parser_node(state: RecruitmentState) -> RecruitmentState:
    """
    LangGraph node: Parse all resume files to extract raw text.
    Reads: resume_file_infos
    Writes: parsed_resumes
    """
    file_infos = state.get("resume_file_infos", [])
    logger.info(f"[Resume Parser] Processing {len(file_infos)} resumes")

    if not file_infos:
        return {**state, "parsed_resumes": []}

    max_workers = min(settings.MAX_RESUME_PROCESSING_WORKERS, len(file_infos), 10)
    parsed: List[ResumeData] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_info = {
            executor.submit(_parse_single_resume, info): info
            for info in file_infos
        }
        for future in as_completed(future_to_info):
            result = future.result()
            parsed.append(result)

    successful = sum(1 for r in parsed if not r.get("error"))
    failed = len(parsed) - successful
    logger.info(f"[Resume Parser] Done: {successful} successful, {failed} failed")

    return {
        **state,
        "parsed_resumes": parsed,
        "processing_stats": {
            **state.get("processing_stats", {}),
            "resumes_parsed": successful,
            "resumes_parse_failed": failed,
        },
    }
