"""Compatibilité dj-stripe ↔ stripe-python ≥ 12.

stripe-python 12+ a retiré certaines méthodes dict-like de `StripeObject`
(notamment `.get()`) qui étaient utilisées implicitement par dj-stripe 2.10.
Sans ce patch, tout webhook process échoue en 500 avec :

    KeyError: 'get'
    File ".../djstripe/models/base.py", line 349, in _find_owner_account
        if data.get("object") == "event":

On ajoute donc une méthode `.get()` dict-like sur `StripeObject` à
l'initialisation de l'app. À retirer quand on upgrade dj-stripe à 2.11+
(qui utilise directement `__getitem__` avec try/except).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def patch_stripe_object_get() -> None:
    """Ajoute `.get(key, default=None)` à `stripe.StripeObject` si absente."""
    try:
        from stripe import StripeObject
    except ImportError:  # pas de stripe installé ⇒ rien à patcher
        return

    if hasattr(StripeObject, 'get') and callable(StripeObject.get):
        # déjà présente (stripe ≤ 11 ou patch déjà appliqué)
        return

    def _get(self, key, default=None):
        """Accesseur dict-like compatible avec dj-stripe legacy."""
        try:
            return self[key]
        except (KeyError, AttributeError):
            return default

    StripeObject.get = _get
    logger.info('Patched stripe.StripeObject.get (compat dj-stripe 2.10 ↔ stripe ≥ 12)')
