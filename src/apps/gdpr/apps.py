"""Application Django pour les endpoints RGPD (export + suppression)."""

from __future__ import annotations

from django.apps import AppConfig


class GdprConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.gdpr'
    verbose_name = 'GDPR'
