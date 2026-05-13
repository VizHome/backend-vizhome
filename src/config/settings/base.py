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
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env('DJANGO_DEBUG')
ALLOWED_HOSTS = env('DJANGO_ALLOWED_HOSTS')

# ─── Applications ─────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.projects',
    'apps.renders',
    'apps.gallery',
    'apps.billing',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('POSTGRES_DB'),
        'USER': env('POSTGRES_USER'),
        'PASSWORD': env('POSTGRES_PASSWORD'),
        'HOST': env('POSTGRES_HOST', default='localhost'),
        'PORT': env('POSTGRES_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
    }
}

# ─── Auth ─────────────────────────────────────────────────────────────────────
# Custom user model — sera défini à l'étape 2 dans apps.accounts.models.User
# AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── DRF ──────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env('DJANGO_CORS_ALLOWED_ORIGINS')
CORS_ALLOW_CREDENTIALS = True

# ─── Celery (étape 3) ─────────────────────────────────────────────────────────
CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

# ─── i18n / TZ ────────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# ─── Static / Media ───────────────────────────────────────────────────────────
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Provider IA (étape 3) ────────────────────────────────────────────────────
# GEMINI_API_KEY = env('GEMINI_API_KEY', default='')
# RENDERS_DEFAULT_PROVIDER = env('RENDERS_DEFAULT_PROVIDER', default='gemini')
