from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing'

    def ready(self) -> None:
        # Patches compat stripe-python ≥ 12 ↔ dj-stripe 2.10 (cf compat.py)
        from .compat import patch_psycopg_json_dumps, patch_stripe_object_get
        patch_stripe_object_get()
        patch_psycopg_json_dumps()

        from . import handlers  # noqa: F401  enregistre les receivers dj-stripe
