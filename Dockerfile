# RHPL eResources service — Cloud Run container.
# Multi-stage: build deps in a throwaway stage, ship a slim runtime image.

FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app
COPY --from=builder /install /usr/local

# Templates and static files live at the repo root and are loaded by Flask
# at runtime via the explicit paths set in src/esources/main.py.
COPY templates/ ./templates/
COPY static/ ./static/

RUN groupadd -r app && useradd -r -g app app && chown -R app:app /app
USER app

EXPOSE 8080
# 2 workers is ample for this traffic; Cloud Run scales out by instance.
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 60 esources.main:app
