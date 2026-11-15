FROM node:26-alpine AS frontend-build

WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Writes to /repo/airtag_sentry/web/static (see frontend/vite.config.ts outDir) -
# the same command and output location local dev uses.
RUN npm run build


# Stay on 3.14-slim until upstream `findmy` lifts its `<3.15` Python cap.
FROM python:3.15-slim

WORKDIR /app

COPY pyproject.toml ./
COPY airtag_sentry ./airtag_sentry
COPY --from=frontend-build /repo/airtag_sentry/web/static ./airtag_sentry/web/static
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=5)"]

ENTRYPOINT ["python", "-m", "airtag_sentry"]
CMD ["serve"]
