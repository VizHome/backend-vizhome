"""Base Django settings — shared between dev and prod.

Environment variables are loaded via django-environ from a .env file at the
project root (one level above `src/`).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ

# ─── Paths ────────────────────────────────────────────────────────────────────
# settings/base.py → settings/ → config/ → src/
SRC_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR = SRC_DIR.parent

# ─── Environment loading ──────────────────────────────────────────────────────
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    DJANGO_CORS_ALLOWED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ─── Applications ─────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "djstripe",
    "drf_spectacular",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.renders",
    "apps.gallery",
    "apps.billing",
    "apps.forum",
    "apps.support",
    "apps.admin_panel",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_otp.middleware.OTPMiddleware",
    # axes doit être en dernier
    "axes.middleware.AxesMiddleware",
]

# Auth backends : axes intercepte les échecs de login pour le verrouillage
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ─── django-axes (lockout après tentatives échouées) ──────────────────────────
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # 15 minutes
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]  # verrouille par combo
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_CALLABLE = "apps.accounts.lockout.api_lockout_response"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

# ─── Auth ─────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@vizhome.fr")

# ─── OAuth providers ──────────────────────────────────────────────────────────
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
# Requis pour le flow `authorization code` (redirect-based) ; pas requis
# pour le flow legacy `id_token` (Google One Tap / SDK JS).
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")
GITHUB_OAUTH_CLIENT_ID = env("GITHUB_OAUTH_CLIENT_ID", default="")
GITHUB_OAUTH_CLIENT_SECRET = env("GITHUB_OAUTH_CLIENT_SECRET", default="")

# ─── Stripe / dj-stripe ───────────────────────────────────────────────────────
# Les clés sont à renseigner dans .env quand un compte Stripe est créé.
# Sans clés, les endpoints /me/subscription/* renverront 503.
STRIPE_LIVE_MODE = env.bool("STRIPE_LIVE_MODE", default=False)
STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY", default="")
STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY", default="")
STRIPE_TEST_PUBLISHABLE_KEY = env("STRIPE_TEST_PUBLISHABLE_KEY", default="")
STRIPE_LIVE_PUBLISHABLE_KEY = env("STRIPE_LIVE_PUBLISHABLE_KEY", default="")

# dj-stripe — synchronise les objets Stripe en DB via webhooks
DJSTRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="whsec_placeholder")
DJSTRIPE_USE_NATIVE_JSONFIELD = True
DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"  # recommandé pour les nouvelles installations
DJSTRIPE_SUBSCRIBER_MODEL = "accounts.User"
DJSTRIPE_WEBHOOK_VALIDATION = "verify_signature"

# ─── Cache (utilisé pour les challenges 2FA) ─────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── DRF ──────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        "register": "5/hour",
        "forgot-password": "3/hour",
        "login": "20/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ─── Celery ───────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
# Schedules sont stockés en DB via django-celery-beat (configurable via admin)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ─── OpenAPI / drf-spectacular ────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "VizHome API",
    "DESCRIPTION": (
        "API REST de la plateforme VizHome — visualisation 3D architecturale "
        "propulsée par IA (Gemini)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
    "COMPONENT_SPLIT_REQUEST": True,
    "CONTACT": {"email": "support@vizhome.fr"},
    "LICENSE": {"name": "Propriétaire"},
    "TAGS": [
        {"name": "Auth", "description": "Login, register, 2FA, OAuth"},
        {"name": "Me", "description": "Profile, préférences, sessions"},
        {"name": "Renders", "description": "Génération IA (Gemini)"},
        {"name": "Projects", "description": "Scènes 3D Three.js"},
        {"name": "Billing", "description": "Abonnements Stripe"},
    ],
}

# ─── i18n / TZ ────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# ─── Static / Media ───────────────────────────────────────────────────────────
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Storage S3-compatible (MinIO) ────────────────────────────────────────────
# USE_S3=True en dev → MinIO local | en prod → MinIO self-hosted ou vraie S3
#
# Côté env on utilise des noms `MINIO_S3_*` (sémantique du projet). Côté Python,
# django-storages lit obligatoirement des settings nommés `AWS_*` — on fait donc
# le mapping ici.
USE_S3 = env.bool("USE_S3", default=False)

if USE_S3:
    # Identifiants d'accès (= MINIO_ROOT_USER/PASSWORD côté serveur MinIO)
    AWS_ACCESS_KEY_ID = env("MINIO_S3_ACCESS_KEY")
    AWS_SECRET_ACCESS_KEY = env("MINIO_S3_SECRET_KEY")
    AWS_STORAGE_BUCKET_NAME = env("MINIO_S3_BUCKET_NAME", default="vizhome-media")
    AWS_S3_REGION_NAME = env("MINIO_S3_REGION", default="us-east-1")

    # Endpoint interne (réseau Docker : http://minio:9000 ; prod : http://minio:9000 aussi)
    AWS_S3_ENDPOINT_URL = env("MINIO_S3_ENDPOINT_URL")

    # Domaine public pour les URLs renvoyées au frontend.
    # Dev : localhost:9000/vizhome-media | Prod : cdn.vizhome.fr (reverse proxy)
    AWS_S3_CUSTOM_DOMAIN = env("MINIO_S3_CUSTOM_DOMAIN", default="")

    AWS_S3_URL_PROTOCOL = env("MINIO_S3_URL_PROTOCOL", default="http:")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None  # la politique d'accès est gérée par le bucket
    AWS_QUERYSTRING_AUTH = False  # URLs publiques, pas de signature
    AWS_S3_ADDRESSING_STYLE = "path"  # MinIO préfère path-style

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
else:
    # Fallback FileSystem (utile en tests et pour démarrer sans MinIO)
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# ─── Provider IA ──────────────────────────────────────────────────────────────
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_IMAGE_MODEL = env("GEMINI_IMAGE_MODEL", default="gemini-2.5-flash-image-preview")
RENDERS_DEFAULT_PROVIDER = env("RENDERS_DEFAULT_PROVIDER", default="gemini")
