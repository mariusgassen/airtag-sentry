FROM node:22-alpine AS frontend-build

WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Writes to /repo/airtag_sentry/web/static (see frontend/vite.config.ts outDir) -
# the same command and output location local dev uses.
RUN npm run build


FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY airtag_sentry ./airtag_sentry
COPY --from=frontend-build /repo/airtag_sentry/web/static ./airtag_sentry/web/static
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir .

COPY config.example.yaml ./

ENTRYPOINT ["python", "-m", "airtag_sentry"]
CMD ["run"]
