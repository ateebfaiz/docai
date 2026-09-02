FROM python:3.11-slim AS base
WORKDIR /app

# Install system deps for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libpq-dev && rm -rf /var/lib/apt/lists/*

# Install production dependencies explicitly (no pyproject.toml build-system dependency)
RUN pip install --no-cache-dir fastapi uvicorn[standard] asyncpg python-multipart alembic celery redis boto3 httpx psycopg2-binary

# Copy source code only (minimal image)
COPY src/ ./src/
COPY .dockerignore ./

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.ai_cli.api:app", "--host", "0.0.0.0", "--port", "8000"]
