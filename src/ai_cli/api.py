"""DocAI — document OCR & extraction API (deployed on Railway)."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

app = FastAPI(
    title="DocAI",
    version="0.1.0",
    description="Upload documents -> OCR in cloud (Railway) -> extracted text.",
)


class DocumentResponse(BaseModel):
    id: str
    name: str
    status: str  # queued | processing | done | failed
    created_at: str
    ocr_text: Optional[str] = None


@app.get("/health")
async def health():
    """Health check for Railway probes."""
    return {"status": "ok", "service": "docai", "version": "0.1.0"}


@app.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(file: UploadFile = File(...)):
    """Upload a document; queue it for OCR processing."""
    doc_id = f"doc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    return DocumentResponse(
        id=doc_id,
        name=file.filename or "unknown",
        status="queued",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/process/{document_id}")
async def trigger_processing(document_id: str):
    """Trigger OCR processing for a queued document."""
    return {"document_id": document_id, "status": "processing", "queued": True}


@app.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str):
    """Get document status and extracted text."""
    return DocumentResponse(
        id=document_id,
        name=f"{document_id}.pdf",
        status="done",
        created_at=datetime.now(timezone.utc).isoformat(),
        ocr_text="[sample] OCR text placeholder — worker integration pending.",
    )
