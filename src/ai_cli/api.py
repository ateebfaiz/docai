"""DocAI FastAPI — document OCR pipeline service with full extraction stack.
Persists to Postgres (DATABASE_URL) when set — Railway/Neon — else falls back to SQLite for local dev.
"""
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from pipeline import run_full_pipeline

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="DocAI", version="0.3.0",
              description="Full OCR & extraction pipeline (adaptive, content-aware)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR = Path(os.environ.get("DB_DIR", "/data"))
DB_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT,
    created_at TEXT,
    doc_type TEXT,
    classification_confidence REAL DEFAULT 0,
    fields TEXT,
    entities TEXT,
    tables TEXT,
    cleaned_text TEXT,
    markdown TEXT,
    source_format TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_docs_created ON documents(created_at);
"""


class _Store:
    """Thin wrapper: Postgres if DATABASE_URL set, else SQLite."""

    def __init__(self):
        self.url = os.environ.get("DATABASE_URL")
        self.backend = "postgres" if self.url else "sqlite"
        if self.backend == "postgres":
            import psycopg2
            self._init_pg(psycopg2)

    def _init_pg(self, psycopg2):
        try:
            conn = psycopg2.connect(self.url)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
            conn.close()
        except Exception as e:
            # Fall back to SQLite if Postgres is unavailable at boot
            print(f"Postgres init failed ({e}); falling back to SQLite")
            self.backend = "sqlite"

    def _pg_conn(self):
        import psycopg2
        return psycopg2.connect(self.url)

    def insert(self, doc: dict):
        if self.backend == "postgres":
            conn = self._pg_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO documents
                           (id, name, status, created_at, doc_type, classification_confidence,
                            fields, entities, tables, cleaned_text, markdown, source_format)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (doc["id"], doc["name"], doc["status"], doc["created_at"],
                         doc.get("doc_type"), doc.get("classification_confidence", 0),
                         json.dumps(doc.get("fields", {})),
                         json.dumps(doc.get("entities", {})),
                         json.dumps(doc.get("tables", [])),
                         doc.get("cleaned_text", ""), doc.get("markdown", ""),
                         doc.get("source_format", "")),
                    )
                conn.commit()
            finally:
                conn.close()
        else:
            import sqlite3
            conn = sqlite3.connect(DB_DIR / "docai.db")
            conn.execute(SCHEMA)
            conn.execute(
                """INSERT INTO documents
                   (id, name, status, created_at, doc_type, classification_confidence,
                    fields, entities, tables, cleaned_text, markdown, source_format)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc["id"], doc["name"], doc["status"], doc["created_at"],
                 doc.get("doc_type"), doc.get("classification_confidence", 0),
                 json.dumps(doc.get("fields", {})),
                 json.dumps(doc.get("entities", {})),
                 json.dumps(doc.get("tables", [])),
                 doc.get("cleaned_text", ""), doc.get("markdown", ""),
                 doc.get("source_format", "")),
            )
            conn.commit()
            conn.close()

    def get(self, doc_id: str) -> Optional[dict]:
        if self.backend == "postgres":
            import psycopg2
            conn = self._pg_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT id,name,status,created_at,doc_type,classification_confidence,
                                  fields,entities,tables,cleaned_text,markdown,source_format
                           FROM documents WHERE id=%s""", (doc_id,))
                    row = cur.fetchone()
            finally:
                conn.close()
        else:
            import sqlite3
            conn = sqlite3.connect(DB_DIR / "docai.db")
            row = conn.execute(
                """SELECT id,name,status,created_at,doc_type,classification_confidence,
                          fields,entities,tables,cleaned_text,markdown,source_format
                   FROM documents WHERE id=?""", (doc_id,)).fetchone()
            conn.close()
        return _row_to_dict(row)

    def list_all(self) -> list[dict]:
        if self.backend == "postgres":
            import psycopg2
            conn = self._pg_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT id,name,status,created_at,doc_type,classification_confidence,
                                  fields,entities,tables,cleaned_text,markdown,source_format
                           FROM documents ORDER BY created_at DESC LIMIT 200""")
                    rows = cur.fetchall()
            finally:
                conn.close()
        else:
            import sqlite3
            conn = sqlite3.connect(DB_DIR / "docai.db")
            rows = conn.execute(
                """SELECT id,name,status,created_at,doc_type,classification_confidence,
                          fields,entities,tables,cleaned_text,markdown,source_format
                   FROM documents ORDER BY created_at DESC LIMIT 200""").fetchall()
            conn.close()
        return [_row_to_dict(r) for r in rows]


_depth = None


def _row_to_dict(row):
    """Convert a row to a dict. Works for both sqlite tuples and psycopg tuples (reordered)."""
    if row is None:
        return None
    cols = ["id", "name", "status", "created_at", "doc_type",
            "classification_confidence", "fields", "entities", "tables",
            "cleaned_text", "markdown", "source_format"]
    d = {c: (v if v is not None else (0 if c == "classification_confidence" else "")) for c, v in zip(cols, row)}
    try:
        d["fields"] = json.loads(d["fields"]) if d.get("fields") else {}
    except Exception:
        d["fields"] = {}
    try:
        d["entities"] = json.loads(d["entities"]) if d.get("entities") else {}
    except Exception:
        d["entities"] = {}
    try:
        d["tables"] = json.loads(d["tables"]) if d.get("tables") else []
    except Exception:
        d["tables"] = []
    return d


store = _Store()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DocumentResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: str
    doc_type: Optional[str] = None
    classification_confidence: float = 0
    fields: Optional[dict] = None
    entities: Optional[dict] = None
    tables_found: int = 0
    page_count: int = 0
    ocr_text: Optional[str] = None
    markdown: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "docai",
        "version": "0.3.0",
        "storage": store.backend,
    }


@app.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(file: UploadFile = File(...)):
    doc_id = f"doc-{uuid.uuid4().hex[:12]}"
    safe_name = Path(file.filename or "upload").name
    ext = Path(safe_name).suffix.lower()

    dest = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    try:
        report = run_full_pipeline(dest)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pipeline failed: {e}")

    doc = {
        "id": doc_id,
        "name": safe_name,
        "status": "done",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "doc_type": report.get("document_type"),
        "classification_confidence": report.get("classification_confidence", 0),
        "fields": report.get("fields", {}),
        "entities": report.get("entities", {}),
        "tables": report.get("tables", []),
        "cleaned_text": report.get("cleaned_text", ""),
        "markdown": report.get("markdown", ""),
        "source_format": ext,
    }
    store.insert(doc)

    return DocumentResponse(
        id=doc_id,
        name=safe_name,
        status="done",
        created_at=doc["created_at"],
        doc_type=doc["doc_type"],
        classification_confidence=doc["classification_confidence"],
        fields=doc["fields"],
        entities=doc["entities"],
        tables_found=len(doc["tables"]),
        page_count=report.get("page_count", 0),
        ocr_text=doc["cleaned_text"][:2000],
        markdown=doc["markdown"][:5000],
    )


@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str):
    d = store.get(document_id)
    if not d:
        raise HTTPException(status_code=404, detail="document not found")
    return _to_response(d)


@app.get("/documents", response_model=list[DocumentResponse])
async def list_documents():
    return [_to_response(d) for d in store.list_all()]


def _to_response(d: dict) -> DocumentResponse:
    return DocumentResponse(
        id=d["id"],
        name=d["name"],
        status=d["status"],
        created_at=d["created_at"],
        doc_type=d.get("doc_type"),
        classification_confidence=d.get("classification_confidence", 0),
        fields=d.get("fields", {}),
        entities=d.get("entities", {}),
        tables_found=len(d.get("tables", [])),
        page_count=int(d.get("page_count", 0) or 0),
        ocr_text=(d.get("cleaned_text") or "")[:2000],
        markdown=(d.get("markdown") or "")[:5000],
    )