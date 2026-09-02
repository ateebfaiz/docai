"""DocAI FastAPI — document OCR pipeline service with full extraction stack."""
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import local pipeline module (same dir in container)
from pipeline import run_full_pipeline

app = FastAPI(title="DocAI", version="0.2.0", description="Full OCR & extraction pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "/data/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR = Path(os.environ.get("DB_DIR", "/data"))
DB_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job store (SQLite file for persistence across restarts)
import sqlite3

DB_PATH = DB_DIR / "docai.db"
JOBS: dict[str, dict] = {}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT,
            created_at TEXT,
            doc_type TEXT,
            entities TEXT,
            cleaned_text TEXT,
            markdown TEXT
        )"""
    )
    return conn


class DocumentResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: str
    doc_type: Optional[str] = None
    entities: Optional[dict] = None
    ocr_text: Optional[str] = None
    markdown: Optional[str] = None
    tables_found: int = 0


@app.get("/health")
async def health():
    """Health check for Railway probes."""
    return {"status": "ok", "service": "docai", "version": "0.2.0"}


@app.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(file: UploadFile = File(...)):
    """Upload a document and process it immediately through the full pipeline."""
    doc_id = f"doc-{uuid.uuid4().hex[:12]}"
    safe_name = Path(file.filename or "upload").name
    dest = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    # Run the full OCR/extraction pipeline
    try:
        report = run_full_pipeline(dest)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pipeline failed: {e}")

    entities = report.get("entities", {})
    conn = _db()
    conn.execute(
        "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
        (
            doc_id, safe_name, "done",
            datetime.now(timezone.utc).isoformat(),
            report.get("document_type"),
            __import__("json").dumps(entities),
            report.get("cleaned_text", ""),
            report.get("markdown", ""),
        ),
    )
    conn.commit()
    conn.close()

    return DocumentResponse(
        id=doc_id,
        name=safe_name,
        status="done",
        created_at=datetime.now(timezone.utc).isoformat(),
        doc_type=report.get("document_type"),
        entities=entities,
        ocr_text=report.get("cleaned_text", "")[:2000],
        markdown=report.get("markdown", "")[:5000],
        tables_found=report.get("tables_found", 0),
    )


@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str):
    """Retrieve a processed document from the store."""
    conn = _db()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    import json
    return DocumentResponse(
        id=row[0], name=row[1], status=row[2], created_at=row[3],
        doc_type=row[4], entities=json.loads(row[5]) if row[5] else {},
        ocr_text=(row[6] or "")[:2000], markdown=(row[7] or "")[:5000],
    )


@app.get("/documents", response_model=list[DocumentResponse])
async def list_documents():
    """List all processed documents."""
    conn = _db()
    rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    conn.close()
    import json
    return [
        DocumentResponse(
            id=r[0], name=r[1], status=r[2], created_at=r[3],
            doc_type=r[4], entities=json.loads(r[5]) if r[5] else {},
            ocr_text=(r[6] or "")[:2000],
        )
        for r in rows
    ]
