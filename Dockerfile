# Stage 1: build frontend
FROM node:25-alpine AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: run backend and serve static frontend
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY main.py ./

# Copy built frontend into static dir (FastAPI serves from ./static)
COPY --from=frontend /app/web/dist ./static

# The container runs as root on purpose: Railway mounts volumes (DATA_DIR=/data) as root, and a
# non-root user cannot write to them (https://docs.railway.com/volumes/reference#caveats).
# Accepted risk, see docs/SECURITY_OPERATIONS.md.

EXPOSE 8000
ENV PORT=8000
CMD sh -c 'uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}'
