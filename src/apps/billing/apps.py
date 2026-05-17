from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing'

    def ready(self) -> None:
        from . import handlers  # noqa: F401  enregistre les receivers dj-stripe
