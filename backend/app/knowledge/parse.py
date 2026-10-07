"""Document parsing and chunking (SPEC §9.1).

PDF text is extracted per page with pypdf and grouped into sections: a line
that looks like a heading (numbered heading or an all-caps banner) starts a
new section, and the section's lines become one chunk attributed to the page
where the section started. DOCX is walked paragraph by paragraph with
python-docx: a heading paragraph sets the current section and each body
paragraph is one chunk. Every chunk keeps its page and section reference so
citations can point at the passage.

No OCR and no table extraction (AGENTS.md DEMO CUT): text layers only. DOCX
has no fixed pagination, so DOCX chunks carry page=None and are cited by
section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_NUMBERED_HEADING = re.compile(r"^\d+(\.\d+)*[.)]?\s+\S")
_MIN_CHUNK_CHARS = 20


@dataclass(frozen=True, slots=True)
class ParsedChunk:
    text: str
    page: int | None
    section: str | None


def _heading_like(line: str) -> bool:
    if len(line) > 64:
        return False
    if _NUMBERED_HEADING.match(line):
        return True
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and line.isupper()


def parse_pdf(path: Path) -> list[ParsedChunk]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks: list[ParsedChunk] = []
    buffer: list[str] = []
    section: str | None = None
    buffer_page: int | None = None
    buffer_section: str | None = None

    def flush() -> None:
        nonlocal buffer
        text = " ".join(part.strip() for part in buffer if part.strip())
        if len(text) >= _MIN_CHUNK_CHARS:
            chunks.append(ParsedChunk(text=text, page=buffer_page, section=buffer_section))
        buffer = []

    for page_no, page in enumerate(reader.pages, start=1):
        for raw in (page.extract_text() or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            if _heading_like(line):
                flush()
                section = line
                continue
            if not buffer:
                buffer_page = page_no
                buffer_section = section
            buffer.append(line)
    flush()
    return chunks


def parse_docx(path: Path) -> list[ParsedChunk]:
    from docx import Document

    document = Document(str(path))
    chunks: list[ParsedChunk] = []
    section: str | None = None
    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        if style.lower().startswith("heading") or style.lower() == "title":
            section = text
            continue
        if len(text) >= _MIN_CHUNK_CHARS:
            chunks.append(ParsedChunk(text=text, page=None, section=section))
    return chunks


def parse_document(path: Path) -> list[ParsedChunk]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix in (".docx", ".dotx"):
        return parse_docx(path)
    raise ValueError(f"unsupported document type: {path.name}")
