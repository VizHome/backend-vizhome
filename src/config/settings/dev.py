"""Development settings — used by default in local environments."""
from .base import *  # noqa: F401, F403

DEBUG = True

# Tolérant en dev : autorise toutes les origines locales
CORS_ALLOW_ALL_ORIGINS = True

# Email console pour ne pas envoyer en dev
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging plus verbeux
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django.db.backends': {'level': 'INFO'},
    },
}
