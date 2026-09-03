FROM python:3.11-slim AS base
WORKDIR /app

# System deps: OCR libs + tesseract + fonts + geometry
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ libpq-dev curl \
    tesseract-ocr tesseract-ocr-eng \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    poppler-utils ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source
COPY src/ ./src/
COPY pipeline.py .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UPLOAD_DIR=/data/uploads
ENV DB_DIR=/data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn src.ai_cli.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
