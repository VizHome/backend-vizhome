"""App config pour le panel admin interne (dashboard staff)."""

from __future__ import annotations

from django.apps import AppConfig


class AdminPanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.admin_panel'

    def ready(self) -> None:
        # Auto-discovery des tâches Celery (admin_panel.snapshot_metrics)
        from . import tasks  # noqa: F401
