"""Development settings — used by default in local environments."""

import environ

from .base import *

env = environ.Env()

DEBUG = True

# Tolérant en dev : autorise toutes les origines locales
CORS_ALLOW_ALL_ORIGINS = True

# Email — envoie vers MailPit (UI http://localhost:8025) par défaut.
# Override via EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# si tu préfères les logs Docker.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="dev@vizhome.local")

# Logging plus verbeux
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "INFO"},
    },
}
