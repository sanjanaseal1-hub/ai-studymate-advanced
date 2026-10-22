"""Document registry + job state (SQLite, standard library) and raw-file storage.

Chroma stores chunk vectors; this stores the document-level record and its processing state:
queued -> processing -> indexed | failed. The raw upload is kept on disk so a failed job can be retried
without re-uploading, and so indexing can run after the HTTP response was already returned.
"""
import hashlib
import sqlite3
import threading
import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from utils import config

QUEUED, PROCESSING, INDEXED, FAILED = "queued", "processing", "indexed", "failed"
_COLUMNS = {"status", "error", "pages", "chunk_count", "characters", "indexed_at"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class DocumentRecord:
    id: str
    user_id: str
    filename: str
    file_type: str
    size_bytes: int
    content_hash: str
    status: str
    error: Optional[str]
    pages: int
    chunk_count: int
    characters: int
    created_at: str
    indexed_at: Optional[str]


class DocumentRepository:
    def __init__(self, db_path: Path, upload_dir: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        upload_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir = upload_dir
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("""CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL, file_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
                pages INTEGER DEFAULT 0, chunk_count INTEGER DEFAULT 0, characters INTEGER DEFAULT 0,
                created_at TEXT NOT NULL, indexed_at TEXT)""")
            self._db.commit()

    def _row(self, row) -> Optional[DocumentRecord]:
        return DocumentRecord(**{f.name: row[f.name] for f in fields(DocumentRecord)}) if row else None

    def create(self, user_id: str, filename: str, file_type: str, data: bytes) -> DocumentRecord:
        doc_id = uuid.uuid4().hex[:12]
        (self.upload_dir / f"{doc_id}.bin").write_bytes(data)
        with self._lock:
            self._db.execute("INSERT INTO documents (id,user_id,filename,file_type,size_bytes,content_hash,status,created_at)"
                             " VALUES (?,?,?,?,?,?,?,?)",
                             (doc_id, user_id, filename, file_type, len(data), hashlib.sha256(data).hexdigest(), QUEUED, utc_now()))
            self._db.commit()
        return self.get(doc_id, user_id)

    def get(self, doc_id: str, user_id: str) -> Optional[DocumentRecord]:
        with self._lock:
            return self._row(self._db.execute("SELECT * FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)).fetchone())

    def list(self, user_id: str) -> list[DocumentRecord]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM documents WHERE user_id=? ORDER BY created_at, rowid", (user_id,)).fetchall()
        return [self._row(r) for r in rows]

    def find_by_hash(self, user_id: str, content_hash: str) -> Optional[DocumentRecord]:
        with self._lock:
            return self._row(self._db.execute("SELECT * FROM documents WHERE user_id=? AND content_hash=? "
                                              "ORDER BY created_at LIMIT 1", (user_id, content_hash)).fetchone())

    def update(self, doc_id: str, **values) -> None:
        unknown = set(values) - _COLUMNS
        if unknown:
            raise ValueError(f"unknown columns: {unknown}")
        assignments = ", ".join(f"{k}=?" for k in values)
        with self._lock:
            self._db.execute(f"UPDATE documents SET {assignments} WHERE id=?", (*values.values(), doc_id))
            self._db.commit()

    def read_file(self, doc_id: str) -> bytes:
        return (self.upload_dir / f"{doc_id}.bin").read_bytes()

    def delete(self, doc_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            self._db.commit()
        (self.upload_dir / f"{doc_id}.bin").unlink(missing_ok=True)

    def recover_interrupted(self) -> int:
        """Jobs that were queued/processing when the server stopped can never finish: mark them failed (user can retry)."""
        with self._lock:
            cur = self._db.execute("UPDATE documents SET status=?, error=? WHERE status IN (?,?)",
                                   (FAILED, "Indexing was interrupted by a server restart. Please retry.", QUEUED, PROCESSING))
            self._db.commit()
            return cur.rowcount

    def ping(self) -> bool:
        with self._lock:
            self._db.execute("SELECT 1").fetchone()
        return True


@lru_cache
def get_document_repository() -> DocumentRepository:
    data_dir = config.get_data_dir()
    return DocumentRepository(data_dir / "documents.db", data_dir / "uploads")
