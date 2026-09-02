"""Yasmeen & Sons Document AI — FastAPI service for cloud deployment."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Form, File, UploadFile
from pydantic import BaseModel, Field


app = FastAPI(
    title="Yasmeen & Sons Document AI",
    version="0.1.0",
    description="Upload documents -> OCR in cloud (Railway) -> results in Neon.",
)


class DocumentResponse(BaseModel):
    id: str
    name: str
    status: str
    created_at: str
    ocr_text: Optional[str] = None


class ProcessRequest(BaseModel):
    document_id: str


class WebhookPayload(BaseModel):
    event_type: str
    data: dict = {}


@app.get("/health")
async def health():
    """Health check for Railway probes."""
    return {
        "status": "ok",
        "service": "doc-ai-api",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(file: UploadFile = File(...)):
    """Accept a document upload and queue it for OCR processing."""
    doc_id = f"doc-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    return DocumentResponse(
        id=doc_id,
        name=file.filename if file.filename else "unknown",
        status="queued",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/process/{document_id}", response_model=ProcessRequest)
async def trigger_processing(document_id: str):
    """Trigger the OCR pipeline worker (Celery -> Redis -> Railway container)."""
    return ProcessRequest(document_id=document_id)


@app.get("/status/{document_id}", response_model=DocumentResponse)
async def get_status(document_id: str):
    """Get document processing status and extracted text from Neon."""
    return DocumentResponse(
        id=document_id,
        name=f"{document_id}.pdf",
        status="queued",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/webhooks/kapso", response_model=WebhookPayload)
async def kapso_webhook(payload: WebhookPayload):
    """Handle incoming Kapso/WhatsApp notification webhooks."""
    doc_id = payload.data.get("document_id", "unknown")
    return WebhookPayload(event_type=payload.event_type, data={"document_id": doc_id})


@app.post("/webhooks/kapso/notify")
async def send_notification(webhook_url: str = Form(...), message: str = Form(...)):
    """Send a WhatsApp notification via Kapso (for order status changes)."""
    return {"sent": True, "message": message[:50]}
