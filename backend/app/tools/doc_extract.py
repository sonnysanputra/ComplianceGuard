"""
Document text extraction for the 'upload an alert' flow.

Pulls plain text out of an uploaded PDF / DOCX / TXT / CSV / EML so the LLM can
extract the structured alert fields from it. Best-effort: unsupported or
unreadable files return an empty string.
"""

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


def extract_text(filename: str, data: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    try:
        if ext == "pdf":
            import fitz  # PyMuPDF
            with fitz.open(stream=data, filetype="pdf") as doc:
                return "\n".join(page.get_text() for page in doc).strip()
        if ext == "docx":
            from docx import Document
            d = Document(BytesIO(data))
            parts = [p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            return "\n".join(parts).strip()
        if ext in ("txt", "md", "csv", "eml", "json"):
            return data.decode("utf-8", "ignore").strip()
        # unknown extension -> try to decode as text
        return data.decode("utf-8", "ignore").strip()
    except Exception as exc:
        logger.warning(f"[doc_extract] could not read {filename}: {exc}")
        return ""
