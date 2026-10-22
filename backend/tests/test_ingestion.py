"""Validation, extraction, cleaning and chunking."""
import pytest

from services.chunking_service import chunk_document, clean_text, split_section, split_text
from services.extraction_service import Page, extract_pages, validate_upload
from utils.errors import DocumentError
from tests.helpers import BIO, COOK, MD_DOC, make_encrypted_pdf, make_pdf

MB = 1024 * 1024


# ---------- upload validation ----------
@pytest.mark.parametrize("name,data,status", [
    ("a.docx", b"hello", 415), ("e.txt", b"  \n", 422), ("big.txt", b"a" * (2 * MB), 413),
    ("fake.pdf", b"this is not a pdf", 422), ("bin.md", b"abc\x00def", 422)])
def test_validate_upload_rejects(name, data, status):
    with pytest.raises(DocumentError) as exc:
        validate_upload(name, data, max_bytes=MB)
    assert exc.value.status_code == status


def test_validate_upload_accepts_supported_types():
    assert validate_upload("a.txt", b"hello", MB) == "txt"
    assert validate_upload("a.MD", b"# Hi\ntext", MB) == "md"
    assert validate_upload("a.markdown", b"# Hi\ntext", MB) == "md"
    assert validate_upload("a.pdf", make_pdf(["x"]), MB) == "pdf"


# ---------- extraction ----------
def test_pdf_pages_txt_and_md_extraction():
    _, pages = extract_pages("d.pdf", make_pdf(["Page one text", "Page two text"]))
    assert [p.number for p in pages] == [1, 2] and "two" in pages[1].text
    assert extract_pages("a.txt", "Café".encode("cp1252"))[1][0].text == "Café"
    assert extract_pages("a.txt", "Café".encode("utf-8"))[1][0].text == "Café"


def test_corrupted_and_encrypted_pdf_have_friendly_errors():
    with pytest.raises(DocumentError, match="corrupted"):
        extract_pages("bad.pdf", b"%PDF-1.4 garbage garbage")
    with pytest.raises(DocumentError, match="password-protected"):
        extract_pages("locked.pdf", make_encrypted_pdf())


def test_markdown_sections_keep_heading_path_and_ignore_code_fences():
    _, sections = extract_pages("g.md", MD_DOC.encode())
    headings = [s.heading for s in sections]
    assert headings == ["Genetics Guide", "Genetics Guide > Mutations", "Genetics Guide > Mutations > Types",
                        "Genetics Guide > Inheritance"]
    mutation = sections[1].text
    assert "# not a heading" in mutation and "x = 1" in mutation       # '#' inside code fence is not a heading


# ---------- cleaning ----------
def test_clean_text_pdf_style():
    raw = "exam-\nple of a wrapped\nline.\x00\n\n\n\nNew   paragraph\u00a0here\r\n"
    assert clean_text(raw) == "example of a wrapped line.\n\nNew paragraph here"


def test_clean_text_markdown_keeps_structure():
    out = clean_text("# Title\n\n- item one\n- item two\n\n\n\nText", repair_wraps=False)
    assert out == "# Title\n\n- item one\n- item two\n\nText"


# ---------- chunking ----------
def sentences(n):
    return " ".join(f"This is sentence number {i} about cells." for i in range(n))


def test_chunks_respect_size_and_split_at_sentences():
    chunks = split_section(sentences(80), 300, 60, min_chars=40)
    assert len(chunks) > 5 and all(len(c) <= 340 for c in chunks)
    assert all(c.rstrip().endswith(".") for c in chunks)


def test_paragraphs_are_kept_together_before_sentence_splitting():
    text = "First paragraph is short.\n\nSecond paragraph is also short.\n\nThird one."
    assert split_section(text, 1000, 100, 10) == [text]               # fits: one chunk, paragraph breaks preserved
    two = split_section("A" * 20 + ". " + "B" * 20 + ".\n\n" + "C" * 30 + ".", 50, 10, 5)
    assert len(two) >= 2 and two[0].startswith("A")


def test_overlap_is_sentence_aligned():
    chunks = split_section(sentences(40), 400, 100, 40)
    assert len(chunks) > 2
    last_sentence_of_first = chunks[0].split(". ")[-1].rstrip(".")
    assert last_sentence_of_first in chunks[1]


def test_oversized_sentence_is_hard_split():
    chunks = split_section("word " * 500, 300, 50, 40)
    assert len(chunks) > 5 and all(len(c) <= 300 for c in chunks)
    with pytest.raises(ValueError):
        split_text("x", 100, 80)


def test_tiny_and_duplicate_chunks_are_removed_and_metadata_kept():
    pages = [Page(1, BIO * 6), Page(2, BIO * 6), Page(3, "ok.")]       # page 2 duplicates page 1, page 3 is tiny
    chunks = chunk_document(pages, "d1", "x.pdf", "pdf", 300, 50, min_chars=40)
    assert {c.page for c in chunks} == {1}
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len({c.text for c in chunks}) == len(chunks) and all(len(c.text) >= 40 for c in chunks)
    assert chunks[0].chunk_id == "d1:0" and chunks[0].filename == "x.pdf"


def test_single_short_document_is_still_indexable():
    assert [c.text for c in chunk_document([Page(None, "Tiny note.")], "d", "n.txt", "txt", 300, 50, 80)] == ["Tiny note."]


def test_markdown_chunks_carry_heading_metadata_and_embedding_text():
    _, sections = extract_pages("g.md", MD_DOC.encode())
    chunks = chunk_document(sections, "d", "g.md", "md", 300, 50, 40)
    types = [c for c in chunks if c.heading and c.heading.endswith("Types")][0]
    assert "Frameshift" in types.text and types.page is None
    assert types.embedding_text.startswith("Genetics Guide > Mutations > Types")


def test_short_markdown_section_with_heading_is_kept_but_headless_fragment_is_dropped():
    pages = [Page(None, "Alleles are inherited from both parents.", "Guide > Inheritance"), Page(None, "12"),
             Page(None, "A longer paragraph of body text that easily passes the minimum chunk length threshold for this test.")]
    chunks = chunk_document(pages, "d", "g.md", "md", 300, 50, min_chars=60)
    assert [c.heading for c in chunks] == ["Guide > Inheritance", None] and all(c.text != "12" for c in chunks)
