# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCOUT_DB_PATH=/app/data/scout.db \
    SCOUT_CORPUS_DIR=/app/corpus \
    SCOUT_INDEX_DIR=/app/corpus/index \
    SCOUT_STATIC_DIR=/app/static \
    SCOUT_REPORTS_DIR=/app/reports \
    SCOUT_REQUIRE_AUTH=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend /app/backend
RUN pip install --no-cache-dir /app/backend

COPY corpus /app/corpus
COPY eval /app/eval
COPY reports /app/reports
COPY scripts /app/scripts
COPY --from=frontend /app/frontend/dist /app/static

RUN chmod +x /app/scripts/docker-entrypoint.sh \
    && mkdir -p /app/data /app/corpus/index \
    && useradd --create-home --uid 10001 scout \
    && chown -R scout:scout /app/data /app/corpus/index

USER scout
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
