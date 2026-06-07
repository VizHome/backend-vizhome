"""Production settings — strict, secrets via environment."""

from __future__ import annotations

from .base import *
from .base import env

DEBUG = False

# ─── Sécurité HTTP ────────────────────────────────────────────────────────────
# Le reverse proxy Traefik fait le TLS termination → on lui fait confiance pour
# X-Forwarded-Proto. Configuration en couches : Traefik durcit les headers
# globaux (cf traefik/dynamic/middlewares.yml), Django redurcit côté app pour
# la défense en profondeur (au cas où le proxy serait contourné).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

# HSTS : 1 an + sous-domaines + preload (à soumettre sur hstspreload.org après mise en prod)
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies : Secure + HttpOnly + SameSite=Lax (Strict casse OAuth redirect-back)
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Anti-MIME sniffing + anti-clickjacking
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Referrer policy : ne leak rien aux sites externes
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Cross-Origin isolation (renforce le sandbox du navigateur)
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# CSRF — origines de confiance pour les form submits cross-site (admin Django,
# webhook tests, etc.). À renseigner via env DJANGO_CSRF_TRUSTED_ORIGINS.
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[
        "https://api.vizhome.fr",
        "https://vizhome.fr",
        "https://www.vizhome.fr",
    ],
)

# ─── Email SMTP ───────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@vizhome.fr")

# ─── Logging structuré (JSON-friendly) ────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# ─── Sentry (error tracking) ──────────────────────────────────────────────────
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="production")

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        send_default_pii=False,
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        profiles_sample_rate=env.float("SENTRY_PROFILES_SAMPLE_RATE", default=0.0),
    )

# ─── OpenTelemetry tracing ────────────────────────────────────────────────────
# No-op si OTEL_EXPORTER_OTLP_ENDPOINT n'est pas défini. Voir config/otel.py
# pour la liste des auto-instrumentations activées.
from config.otel import init_otel  # noqa: E402

init_otel()
