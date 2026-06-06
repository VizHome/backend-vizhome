"""App config pour le forum communautaire."""

from __future__ import annotations

from django.apps import AppConfig


class ForumConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.forum"

    def ready(self) -> None:
        # Importe les signals — incrémente/décrémente les compteurs
        # topics_count / replies_count en cascade.
        from . import signals  # noqa: F401
