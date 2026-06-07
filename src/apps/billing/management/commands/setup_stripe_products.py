"""Crée/synchronise les Products et Prices Stripe à partir de PLAN_CONFIG.

Usage :
    python manage.py setup_stripe_products
    python manage.py setup_stripe_products --dry-run

Idempotent : utilise les lookup_keys pour mettre à jour si déjà existant.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.billing.plans import get_billable_plans
from apps.billing.stripe_client import StripeNotConfigured, get_stripe_client


class Command(BaseCommand):
    help = 'Crée/met à jour les Products et Prices Stripe selon PLAN_CONFIG'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche ce qui serait créé sans appeler Stripe',
        )

    def handle(self, *args, dry_run: bool = False, **opts) -> None:
        try:
            stripe = get_stripe_client()
        except StripeNotConfigured as e:
            raise CommandError(str(e))

        billable = get_billable_plans()
        if not billable:
            self.stdout.write(self.style.WARNING('Aucun plan billable dans PLAN_CONFIG.'))
            return

        for plan_name, config in billable.items():
            lookup_key = config['stripe_lookup_key']
            product_name = f'VizHome {config["label"]}'

            self.stdout.write(f'\n→ Plan « {plan_name} »')
            self.stdout.write(f'  Product   : {product_name}')
            self.stdout.write(f'  Lookup    : {lookup_key}')
            self.stdout.write(f'  Prix      : {config["price_eur"] / 100:.2f} € / mois')

            if dry_run:
                self.stdout.write(self.style.WARNING('  [dry-run] Skip Stripe API calls'))
                continue

            # 1. Find or create Product (par metadata.plan)
            existing = stripe.Product.search(query=f'metadata["plan"]:"{plan_name}"', limit=1)
            if existing.data:
                product = existing.data[0]
                self.stdout.write(f'  ✓ Product existant : {product.id}')
            else:
                product = stripe.Product.create(
                    name=product_name,
                    description=config['description'],
                    metadata={'plan': plan_name},
                )
                self.stdout.write(self.style.SUCCESS(f'  + Product créé : {product.id}'))

            # 2. Find Price by lookup_key
            existing_prices = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
            if existing_prices.data:
                price = existing_prices.data[0]
                self.stdout.write(f'  ✓ Price existant : {price.id}')
                # Si le montant a changé, on archive l'ancienne et on en crée une nouvelle
                if price.unit_amount != config['price_eur']:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  Montant changé ({price.unit_amount} → {config["price_eur"]} cents)'
                        )
                    )
                    stripe.Price.modify(price.id, lookup_key=f'{lookup_key}_archived')
                    new_price = stripe.Price.create(
                        product=product.id,
                        unit_amount=config['price_eur'],
                        currency='eur',
                        recurring={'interval': 'month'},
                        lookup_key=lookup_key,
                        transfer_lookup_key=True,
                    )
                    self.stdout.write(self.style.SUCCESS(f'  + Nouvelle Price : {new_price.id}'))
            else:
                price = stripe.Price.create(
                    product=product.id,
                    unit_amount=config['price_eur'],
                    currency='eur',
                    recurring={'interval': 'month'},
                    lookup_key=lookup_key,
                )
                self.stdout.write(self.style.SUCCESS(f'  + Price créée : {price.id}'))

        self.stdout.write(self.style.SUCCESS('\n✓ Setup Stripe terminé.'))
