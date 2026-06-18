from pathlib import Path
from typing import Tuple
from loguru import logger


def parse_pdf(file_path: str) -> Tuple[str, int]:
    """
    Parse a PDF file and extract text content.
    Returns (text, page_count).
    Tries pdfplumber first, falls back to pymupdf.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    # Try pdfplumber first (better for text-based PDFs)
    try:
        return _parse_with_pdfplumber(file_path)
    except Exception as e:
        logger.warning(f"pdfplumber failed for {file_path}: {e}, trying pymupdf")

    # Fallback to pymupdf (better for scanned/image PDFs)
    try:
        return _parse_with_pymupdf(file_path)
    except Exception as e:
        logger.error(f"pymupdf also failed for {file_path}: {e}")
        raise ValueError(f"Could not parse PDF: {file_path}") from e


def _parse_with_pdfplumber(file_path: str) -> Tuple[str, int]:
    import pdfplumber

    texts = []
    page_count = 0
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text:
                texts.append(text.strip())

            # Also extract tables as text if present
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row_text = " | ".join(cell or "" for cell in row if cell)
                    if row_text.strip():
                        texts.append(row_text.strip())

    return "\n\n".join(texts), page_count


def _parse_with_pymupdf(file_path: str) -> Tuple[str, int]:
    import fitz  # pymupdf

    texts = []
    doc = fitz.open(file_path)
    page_count = len(doc)
    for page in doc:
        text = page.get_text("text")
        if text and text.strip():
            texts.append(text.strip())
    doc.close()
    return "\n\n".join(texts), page_count
