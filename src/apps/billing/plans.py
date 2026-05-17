"""Source de vérité des plans VizHome.

Le mapping vers Stripe se fait via `stripe_lookup_key` — un identifiant
permanent attaché à une Price Stripe, qui survit aux changements de prix
(versioning Stripe). La management command `setup_stripe_products` crée les
Products et Prices côté Stripe avec ces lookup keys.
"""
from __future__ import annotations

from typing import TypedDict


class PlanConfig(TypedDict):
    label: str
    description: str
    price_eur: int | None  # cents EUR / mois, None = sur devis
    renders_limit: int
    storage_limit_bytes: int
    stripe_lookup_key: str | None
    stripe_product_id: str  # nom interne pour le Product Stripe


PLAN_CONFIG: dict[str, PlanConfig] = {
    'free': {
        'label': 'Gratuit',
        'description': 'Pour découvrir VizHome',
        'price_eur': 0,
        'renders_limit': 5,
        'storage_limit_bytes': 1 * 1024**3,  # 1 GB
        'stripe_lookup_key': None,
        'stripe_product_id': '',
    },
    'pro': {
        'label': 'Pro',
        'description': '50 rendus/mois, 5 GB de stockage',
        'price_eur': 1900,  # 19.00 €
        'renders_limit': 50,
        'storage_limit_bytes': 5 * 1024**3,  # 5 GB
        'stripe_lookup_key': 'vizhome_pro_monthly',
        'stripe_product_id': 'vizhome_pro',
    },
    'enterprise': {
        'label': 'Entreprise',
        'description': 'Quotas étendus + support prioritaire',
        'price_eur': 9900,  # 99.00 € (à ajuster, sur devis IRL)
        'renders_limit': 9999,
        'storage_limit_bytes': 1024 * 1024**3,  # 1 TB
        'stripe_lookup_key': 'vizhome_enterprise_monthly',
        'stripe_product_id': 'vizhome_enterprise',
    },
}


def get_plan_by_lookup_key(lookup_key: str) -> str | None:
    """Retourne la clé interne du plan ('pro', 'enterprise') depuis un lookup_key Stripe."""
    for plan_name, config in PLAN_CONFIG.items():
        if config['stripe_lookup_key'] == lookup_key:
            return plan_name
    return None


def get_billable_plans() -> dict[str, PlanConfig]:
    """Renvoie uniquement les plans payants (= ceux à créer côté Stripe)."""
    return {k: v for k, v in PLAN_CONFIG.items() if v['stripe_lookup_key']}
