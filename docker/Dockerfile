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

# ─── Build args injectés via docker build-push-action (release.yml) ─────
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=dev

# ─── OCI image labels ────────────────────────────────────────────────────
# Standard : https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="VizHome Backend" \
      org.opencontainers.image.description="API Django REST pour VizHome — \
plateforme SaaS de génération de rendus 3D par IA (Gemini), import GLB/OBJ/FBX, \
forum communautaire, support helpdesk, billing Stripe, admin panel staff." \
      org.opencontainers.image.vendor="VizHome" \
      org.opencontainers.image.authors="VizHome team" \
      org.opencontainers.image.url="https://vizhome.fr" \
      org.opencontainers.image.documentation="https://github.com/VizHome/backend-vizhome/blob/main/README.md" \
      org.opencontainers.image.source="https://github.com/VizHome/backend-vizhome" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="docker.io/library/python:3.13-slim" \
      org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.version=$VERSION \
      # Labels custom VizHome
      fr.vizhome.component="backend" \
      fr.vizhome.runtime="python-3.13" \
      fr.vizhome.framework="django-6"

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
