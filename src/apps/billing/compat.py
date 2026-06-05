"""Compatibilité dj-stripe ↔ stripe-python ≥ 12.

stripe-python 12+ a changé l'API publique de `StripeObject` :
- Retiré la méthode dict-like `.get()` (cassait `data.get("object")`)
- Les objets imbriqués (`Account`, etc.) ne sont plus auto-convertis en
  dict avant sérialisation → JSONField PostgreSQL plante avec
  `TypeError: Object of type Account is not JSON serializable`

Ces deux patches restaurent la compat sans toucher au code dj-stripe.
À retirer quand on upgrade dj-stripe à 2.11+ (qui supporte stripe 12+ nativement).
"""
from __future__ import annotations

import json
import logging
from typing import Any

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


def _stripe_aware_default(obj: Any) -> Any:
    """JSON encoder fallback : convertit récursivement les StripeObject en dict."""
    try:
        from stripe import StripeObject
    except ImportError:
        StripeObject = None  # type: ignore

    if StripeObject is not None and isinstance(obj, StripeObject):
        # to_dict_recursive() est dispo sur les vieux SDK ; sinon fallback iter
        if hasattr(obj, 'to_dict_recursive'):
            return obj.to_dict_recursive()
        return {k: obj[k] for k in obj}  # __iter__ + __getitem__ existent toujours

    # ISO format pour datetime, fallback string pour le reste
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


def _stripe_aware_dumps(value: Any, **kwargs: Any) -> str:
    """`json.dumps` avec le fallback Stripe-aware."""
    return json.dumps(value, default=_stripe_aware_default, **kwargs)


def patch_psycopg_json_dumps() -> None:
    """Remplace le `dumps` global de psycopg pour gérer les StripeObject.

    psycopg utilise `json.dumps` par défaut sur les JSONField → plante quand
    dj-stripe lui passe un `Account` Stripe brut. On lui donne une version
    avec un `default=` qui convertit les StripeObject en dict.

    Note : c'est un setting GLOBAL psycopg, donc affecte toute l'app —
    mais le comportement reste identique pour les types standards.
    """
    try:
        from psycopg.types.json import set_json_dumps
    except ImportError:
        return

    set_json_dumps(_stripe_aware_dumps)
    logger.info('Patched psycopg JSON dumps (compat Stripe Account → dict)')
