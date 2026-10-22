"""STAGE 1 - VALIDATION + TEXT EXTRACTION for PDF, TXT and Markdown.

Returns a list of `Page` objects (a page for PDFs, a heading-delimited section for Markdown,
one block for TXT) so page numbers and section headings survive into chunk metadata.
"""
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from utils.errors import DocumentError

logger = logging.getLogger("studymate.extraction")

SUPPORTED_TYPES = {".txt": "txt", ".pdf": "pdf", ".md": "md", ".markdown": "md"}
SUPPORTED_LABEL = ".pdf, .txt or .md"
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass
class Page:
    number: Optional[int]          # 1-based for PDF, None otherwise
    text: str
    heading: Optional[str] = None  # Markdown: "Chapter > Section"


def get_file_type(filename: str) -> str:
    file_type = SUPPORTED_TYPES.get(Path(filename).suffix.lower())
    if not file_type:
        raise DocumentError(415, f"'{filename}' is not supported. Please upload {SUPPORTED_LABEL} files only.")
    return file_type


def validate_upload(filename: str, data: bytes, max_bytes: int) -> str:
    """Cheap checks done at upload time. Returns the file type or raises DocumentError."""
    file_type = get_file_type(filename)
    if len(data) > max_bytes:
        raise DocumentError(413, f"'{filename}' is too large. The limit is {max_bytes // (1024 * 1024)} MB per file.")
    if not data.strip():
        raise DocumentError(422, f"'{filename}' is empty.")
    if file_type == "pdf":
        if not data.lstrip().startswith(b"%PDF-"):
            raise DocumentError(422, f"'{filename}' is not a valid PDF file.")
    else:
        _decode_text(filename, data)  # rejects binary content
    return file_type


def _decode_text(filename: str, data: bytes) -> str:
    if b"\x00" in data:
        raise DocumentError(422, f"'{filename}' does not look like a text file (binary content).")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")  # common for Windows-saved files
        if text.count("\ufffd") > len(text) * 0.05:
            raise DocumentError(422, f"'{filename}' contains unreadable characters.")
        return text


def extract_pages(filename: str, data: bytes) -> tuple[str, list[Page]]:
    """Return (file_type, pages). Raises DocumentError with a friendly message on any problem."""
    file_type = get_file_type(filename)
    if not data.strip():
        raise DocumentError(422, f"'{filename}' is empty.")
    if file_type == "pdf":
        return file_type, _extract_pdf(filename, data)
    text = _decode_text(filename, data)
    return file_type, (_extract_markdown(text) if file_type == "md" else [Page(None, text)])


def _extract_markdown(text: str) -> list[Page]:
    """Split Markdown into sections at ATX headings (# ...), ignoring '#' inside code fences."""
    sections: list[Page] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append(Page(None, content, " > ".join(h for _, h in stack) or None))
        body.clear()

    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        match = None if in_fence else HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group(2)))
        else:
            body.append(line)
    flush()
    return sections


def _extract_pdf(filename: str, data: bytes) -> list[Page]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")  # many PDFs are "encrypted" with an empty password
            except Exception:
                unlocked = 0
            if not unlocked:
                raise DocumentError(422, f"'{filename}' is password-protected and cannot be read.")
        pages = []
        for number, pdf_page in enumerate(reader.pages, start=1):
            try:
                pages.append(Page(number, pdf_page.extract_text() or ""))
            except Exception:  # one bad page should not lose the whole document
                logger.warning("Could not read page %s of %s", number, filename)
        return pages
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(422, f"'{filename}' could not be read. The PDF may be corrupted.",
                            f"PDF parse failure: {type(exc).__name__}: {exc}")
