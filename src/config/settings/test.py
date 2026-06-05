"""Settings utilisés par pytest — désactive le storage S3 pour ne pas hit MinIO."""

import tempfile

from .dev import *  # noqa: F403  (re-export glob volontaire de la config dev)

# Force FileSystem storage en tests (ignore USE_S3)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Storage temporaire dans /tmp pour ne pas polluer media/
MEDIA_ROOT = tempfile.mkdtemp(prefix="vizhome_test_")

# Cache local (évite Redis en tests, pour éviter les fuites entre runs)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Désactive axes en tests qui ne testent pas spécifiquement axes (optionnel)
# AXES_ENABLED = False  # commenté car on a des tests qui valident axes
