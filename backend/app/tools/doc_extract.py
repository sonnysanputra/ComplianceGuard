"""
Document text extraction for the 'upload an alert / statement' flow.

Pulls plain text out of an uploaded PDF / DOCX / TXT / CSV so the LLM can extract
the alert, the customer profile, and the transactions.

For PDFs we don't use a naive get_text() -- on a real bank statement that flattens
the table into a single column and the debit/credit distinction is lost. Instead we
reconstruct the visual ROWS from word coordinates (cluster by y, order by x), so each
transaction becomes one line: `date  description  amount  running-balance`. The LLM can
then derive direction from the running-balance delta, which works across bank layouts.

Best-effort: unsupported or image-only (scanned) files return an empty string, and the
caller surfaces a clear "scanned PDF / no text layer" message.
"""

import logging
from io import BytesIO

logger = logging.getLogger(__name__)

_Y_BAND = 3.0  # points; lines are ~17pt apart, so this clusters a row without merging rows


def _pdf_rows(data: bytes) -> str:
    """Reconstruct visual rows from word positions, page by page."""
    import fitz  # PyMuPDF

    out: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            words = page.get_text("words")  # (x0, y0, x1, y1, text, block, line, word_no)
            if not words:
                continue
            bands: dict[int, list[tuple[float, str]]] = {}
            for x0, y0, _x1, _y1, text, *_ in words:
                if text.strip():
                    bands.setdefault(round(y0 / _Y_BAND), []).append((x0, text))
            for key in sorted(bands):
                line = " ".join(w for _, w in sorted(bands[key], key=lambda p: p[0])).strip()
                if line:
                    out.append(line)
    return "\n".join(out)


def extract_text(filename: str, data: bytes) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    try:
        if ext == "pdf":
            return _pdf_rows(data).strip()
        if ext == "docx":
            from docx import Document
            d = Document(BytesIO(data))
            parts = [p.text for p in d.paragraphs]
            for t in d.tables:
                for row in t.rows:
                    parts.append("  ".join(c.text for c in row.cells))
            return "\n".join(parts).strip()
        if ext in ("txt", "md", "csv", "eml", "json"):
            return data.decode("utf-8", "ignore").strip()
        # unknown extension -> try to decode as text
        return data.decode("utf-8", "ignore").strip()
    except Exception as exc:
        logger.warning(f"[doc_extract] could not read {filename}: {exc}")
        return ""
