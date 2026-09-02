FROM python:3.11-slim AS base
WORKDIR /app

# Install system deps for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Install production dependencies explicitly (no pyproject.toml build-system dependency)
RUN pip install --no-cache-dir fastapi uvicorn[standard] asyncpg python-multipart alembic celery redis boto3 httpx psycopg2-binary

# Copy source code only (minimal image)
COPY src/ ./src/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Bind to Railway-injected PORT env var (defaults to 8000 locally)
CMD ["sh", "-c", "uvicorn src.ai_cli.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
