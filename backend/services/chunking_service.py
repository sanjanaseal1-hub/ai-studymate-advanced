"""STAGES 2-3 - CLEANING and STRUCTURE-AWARE CHUNKING.

Strategy (see RAG_ARCHITECTURE.md): sections (PDF page / Markdown heading) are never mixed; inside a
section we pack whole paragraphs up to CHUNK_SIZE; an oversized paragraph is split at sentences; an
oversized sentence is hard-split as a last resort. Chunks start with a sentence-aligned overlap tail from
the previous chunk. Duplicate chunks and tiny headless fragments are removed.
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from services.extraction_service import Page

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    chunk_id: str            # "<document_id>:<chunk_index>"  (deterministic -> re-indexing overwrites, never duplicates)
    document_id: str
    filename: str
    file_type: str
    page: Optional[int]      # PDF page, None otherwise
    heading: Optional[str]   # Markdown section path, None otherwise
    chunk_index: int         # position in the document, 0-based
    text: str

    @property
    def embedding_text(self) -> str:
        """Text that is embedded / lexically scored: the section heading gives the chunk its topic."""
        return f"{self.heading}\n\n{self.text}" if self.heading else self.text


def clean_text(text: str, repair_wraps: bool = True) -> str:
    """Normalise extracted text. repair_wraps=False keeps line structure (used for Markdown)."""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)   # control characters
    if repair_wraps:
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)               # words hyphenated across lines
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)               # PDF/TXT hard line wraps -> space
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)                         # keep paragraph breaks
    return text.strip()


def split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Last-resort hard splitter: sliding window that prefers sentence/word boundaries."""
    if chunk_size <= 0 or not 0 <= overlap < chunk_size / 2:
        raise ValueError("chunk_size must be > 0 and overlap must be less than half of chunk_size")
    pieces, start, length = [], 0, len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            earliest = start + int(chunk_size * 0.6)
            cut = max(text.rfind(marker, earliest, end) for marker in (". ", "? ", "! ", "\n\n"))
            if cut != -1:
                end = cut + 1
            elif (space := text.rfind(" ", earliest, end)) != -1:
                end = space
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= length:
            break
        start = end - overlap
        next_space = text.find(" ", start, end)
        if start > 0 and text[start - 1] != " " and next_space != -1:
            start = next_space + 1
    return pieces


def _overlap_tail(text: str, overlap: int) -> str:
    """Last ~`overlap` characters of a chunk, trimmed to start at a sentence (or word) boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return ""
    tail = text[-overlap:]
    match = SENTENCE_SPLIT.search(tail)
    if match:
        return tail[match.end():].strip()
    space = tail.find(" ")
    return tail[space + 1:].strip() if space != -1 else ""


def _paragraph_units(paragraph: str, size: int, overlap: int) -> list[str]:
    """A paragraph that fits is one unit; a long one is packed from sentences; a huge sentence is hard-split."""
    if len(paragraph) <= size:
        return [paragraph]
    limit = max(size - overlap, size // 2)  # leave room so the overlap tail still fits in front of the next unit
    units, current = [], ""
    for sentence in SENTENCE_SPLIT.split(paragraph):
        if len(sentence) > size:
            if current:
                units.append(current)
                current = ""
            units.extend(split_text(sentence, size, overlap))
        elif current and len(current) + 1 + len(sentence) > limit:
            units.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        units.append(current)
    return units


def split_section(text: str, size: int, overlap: int, min_chars: int) -> list[str]:
    """Pack paragraphs into chunks of <= size characters (plus small merges of tiny leftovers)."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for unit in (u for p in paragraphs for u in _paragraph_units(p, size, overlap)):
        if current and len(current) + 2 + len(unit) > size:
            chunks.append(current)
            tail = _overlap_tail(current, overlap)
            current = f"{tail} {unit}" if tail and len(tail) + 1 + len(unit) <= size else unit
        else:
            current = f"{current}\n\n{unit}" if current else unit
    if current:
        chunks.append(current)
    merged: list[str] = []
    for chunk in chunks:  # fold tiny chunks into their neighbour instead of indexing them alone
        if merged and len(chunk) < min_chars and len(merged[-1]) + 2 + len(chunk) <= size + min_chars:
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)
    if len(merged) > 1 and len(merged[0]) < min_chars:
        merged[1] = f"{merged[0]}\n\n{merged[1]}"
        merged.pop(0)
    return merged


def chunk_document(pages: list[Page], document_id: str, filename: str, file_type: str,
                   size: int, overlap: int, min_chars: int) -> list[Chunk]:
    """Chunk every page/section separately (keeps page + heading metadata exact), drop duplicates and tiny chunks."""
    found: list[tuple[Page, str]] = []
    seen: set[str] = set()
    for page in pages:
        for piece in split_section(page.text, size, overlap, min_chars):
            key = hashlib.sha1(" ".join(piece.lower().split()).encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                found.append((page, piece))
    if len(found) > 1:
        # Drop tiny fragments (stray page numbers, "Figure 2") but never a short section that has a heading:
        # "## Inheritance + one sentence" is real content. A document with a single short chunk stays indexable.
        found = [f for f in found if len(f[1]) >= min_chars or f[0].heading] or found
    return [Chunk(f"{document_id}:{i}", document_id, filename, file_type, page.number, page.heading, i, piece)
            for i, (page, piece) in enumerate(found)]
