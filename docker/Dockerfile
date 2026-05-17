# syntax=docker/dockerfile:1.7

# =========================================================
# Stage 1 — builder : compile dependencies dans un venv
# =========================================================
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Outils de compilation pour les wheels qui en ont besoin (psycopg, Pillow…)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crée un venv isolé qu'on copiera dans le stage runner
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY src/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# =========================================================
# Stage 2 — runner : image minimale (~150 MB)
# =========================================================
FROM python:3.13-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# Runtime deps uniquement (libpq pour psycopg + postgresql-client pour pg_isready
# + curl pour le HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copie le venv depuis le stage builder
COPY --from=builder /opt/venv /opt/venv

# User non-root
RUN groupadd -r vizhome --gid 1000 \
    && useradd -r -g vizhome --uid 1000 --create-home --shell /bin/bash vizhome

# Code source + entrypoint
COPY --chown=vizhome:vizhome src/ /app/
COPY --chown=vizhome:vizhome docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER vizhome
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# Gunicorn par défaut — override avec `celery -A config worker` pour les workers
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "60", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
