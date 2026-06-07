"""Application Django pour l'endpoint public /contact/."""

from __future__ import annotations

from django.apps import AppConfig


class ContactConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contact'
    verbose_name = 'Contact'
