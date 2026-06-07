"""Wrapper Stripe : configure la clé API et expose des helpers haut niveau."""

from __future__ import annotations

import stripe
from django.conf import settings


class StripeNotConfigured(Exception):
    """Levée quand on tente une opération Stripe sans clé API configurée."""


def get_stripe_client():
    """Retourne le module stripe configuré avec la bonne clé API.

    Selon STRIPE_LIVE_MODE, utilise les clés test ou live.
    """
    key = (
        settings.STRIPE_LIVE_SECRET_KEY
        if settings.STRIPE_LIVE_MODE
        else settings.STRIPE_TEST_SECRET_KEY
    )
    if not key:
        mode = 'live' if settings.STRIPE_LIVE_MODE else 'test'
        raise StripeNotConfigured(
            f'Stripe API key absente (STRIPE_{mode.upper()}_SECRET_KEY). '
            f'Configure Stripe dans .env pour activer le billing.'
        )
    stripe.api_key = key
    return stripe


def is_configured() -> bool:
    """Indique si Stripe est utilisable (sans lever)."""
    key = (
        settings.STRIPE_LIVE_SECRET_KEY
        if settings.STRIPE_LIVE_MODE
        else settings.STRIPE_TEST_SECRET_KEY
    )
    return bool(key)
