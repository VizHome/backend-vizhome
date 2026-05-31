"""App config pour le panel admin interne (dashboard staff)."""
from __future__ import annotations

from django.apps import AppConfig


class AdminPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.admin_panel'
