from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing'

    def ready(self) -> None:
        # Patch compat stripe-python ≥ 12 ↔ dj-stripe 2.10
        # (sinon webhook process 500 avec KeyError 'get')
        from .compat import patch_stripe_object_get
        patch_stripe_object_get()

        from . import handlers  # noqa: F401  enregistre les receivers dj-stripe
