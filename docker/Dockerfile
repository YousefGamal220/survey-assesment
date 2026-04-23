# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.12-slim

FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.1.4

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}" \
    && poetry self add poetry-plugin-export

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# Build /opt/venv with main deps only. poetry-plugin-export is required on
# Poetry 2.x — `poetry export` was removed from core.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && poetry export --without-hashes --only main -f requirements.txt > /tmp/requirements.txt \
    && /opt/venv/bin/pip install -r /tmp/requirements.txt


FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.dev

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

# Create app-writable scratch paths. Fresh named volumes mounted here inherit
# these permissions — previously-created volumes stay root-owned and must be
# chowned once manually (or recreated).
RUN chmod +x docker/entrypoint.sh \
 && mkdir -p /app/staticfiles /var/celery \
 && chown -R app:app /app/staticfiles /var/celery

USER app

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["web"]
