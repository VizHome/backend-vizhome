"""App support — système de tickets utilisateur ↔ staff."""

from django.apps import AppConfig


class SupportConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.support'
    verbose_name = 'Support'
