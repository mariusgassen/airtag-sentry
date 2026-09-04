FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY airtag_sentry ./airtag_sentry

RUN pip install --no-cache-dir .

COPY config.example.yaml ./

ENTRYPOINT ["python", "-m", "airtag_sentry"]
CMD ["run"]
