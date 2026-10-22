"""Shared test helpers. FakeEmbedder/FakeLLM exist ONLY for tests: the app always uses real Gemini."""
import hashlib
import re

from services.embedding_service import EmbeddingClient
from services.llm_client import LLMClient

STOP = {"the", "is", "what", "and", "are", "how", "does", "for", "with", "that", "this", "from", "into", "can", "its"}
DIM = 128


def fake_vector(text: str) -> list[float]:
    vec = [0.0] * DIM
    for word in re.findall(r"[a-z]{3,}", text.lower()):
        if word not in STOP:
            vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    return vec


class FakeEmbedder(EmbeddingClient):
    def __init__(self, error=None):
        self.error, self.calls = error, 0

    async def embed_documents(self, texts):
        self.calls += 1
        if self.error:
            raise self.error
        return [fake_vector(t) for t in texts]

    async def embed_query(self, text):
        if self.error:
            raise self.error
        return fake_vector(text)


class FakeLLM(LLMClient):
    """Returns `text`; stream() yields it word by word."""
    def __init__(self, text="DNA replication copies DNA [1].", error=None):
        self.text, self.error, self.prompt, self.calls, self.temperature = text, error, None, 0, None

    async def generate(self, system_instruction, prompt, temperature=None):
        self.calls += 1
        self.prompt, self.temperature = prompt, temperature
        if self.error:
            raise self.error
        return self.text

    async def stream(self, system_instruction, prompt, temperature=None):
        self.calls += 1
        self.prompt, self.temperature = prompt, temperature
        if self.error:
            raise self.error
        for word in self.text.split(" "):
            yield word + " "


def make_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF, one text line per page (no extra libraries)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)


def make_encrypted_pdf() -> bytes:
    import io
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt("secret", algorithm="RC4-128")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


BIO = ("DNA replication is the process by which a cell copies its DNA before dividing. "
       "The enzyme helicase unwinds the double helix and DNA polymerase builds new strands. ")
COOK = ("Sourdough bread needs flour, water, salt and a fermented starter. "
        "Knead the dough, let it rise overnight, then bake in a hot oven until golden. ")
MD_DOC = """# Genetics Guide

Intro paragraph about heredity and why genes matter for every living organism.

## Mutations

A mutation is a change in the DNA sequence. Some mutations are harmless while others alter proteins.

```python
# not a heading
x = 1
```

### Types

Point mutations change one base. Frameshift mutations insert or delete bases and shift the reading frame.

## Inheritance

Alleles are inherited from both parents following Mendel's laws of segregation.
"""
