"""Crée ou met à jour le WebhookEndpoint local pour dev avec Stripe CLI.

Depuis dj-stripe 2.x, le webhook endpoint exige un objet `WebhookEndpoint` en DB
avec un UUID stable. L'URL devient `/webhooks/stripe/webhook/<uuid>/`.

Cette commande crée un endpoint "local-dev" avec :
- secret = settings.DJSTRIPE_WEBHOOK_SECRET (lu depuis STRIPE_WEBHOOK_SECRET du .env)
- enabled events = '*' (tous)
- UUID stable (ne change pas entre les runs)

Usage :
    docker compose exec api python manage.py setup_webhook_endpoint

Output : affiche l'URL complète à utiliser dans `stripe listen --forward-to`.
"""
from __future__ import annotations

import uuid as uuid_module
from urllib.parse import urljoin

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from djstripe.models import WebhookEndpoint


class Command(BaseCommand):
    help = 'Crée le WebhookEndpoint local pour Stripe CLI (dev only).'

    NAME = 'local-dev'

    def handle(self, *args, **options):
        secret = getattr(settings, 'DJSTRIPE_WEBHOOK_SECRET', '')
        if not secret or secret == 'whsec_placeholder':  # noqa: S105
            raise CommandError(
                'STRIPE_WEBHOOK_SECRET absent ou placeholder dans .env.\n'
                "Lance d'abord `stripe listen --forward-to localhost:8000/...`\n"
                'puis copie le `whsec_xxxx` affiché dans .env, puis '
                '`docker compose up -d --force-recreate api`.',
            )

        # On essaye de réutiliser l'endpoint existant pour garder l'UUID stable
        endpoint = WebhookEndpoint.objects.filter(djstripe_owner_account__isnull=True).first()
        if endpoint is None:
            endpoint = WebhookEndpoint(
                djstripe_uuid=uuid_module.uuid4(),
                url='http://localhost:8000/webhooks/stripe/',
                secret=secret,
                enabled_events=['*'],
                api_version='2020-08-27',
                metadata={'source': 'setup_webhook_endpoint command'},
            )
            endpoint.save()
            created = True
        else:
            endpoint.secret = secret  # rafraîchit le secret au cas où
            endpoint.save(update_fields=['secret', 'djstripe_updated'])
            created = False

        full_url = urljoin(
            'http://localhost:8000/',
            f'webhooks/stripe/webhook/{endpoint.djstripe_uuid}/',
        )

        prefix = '✓ Créé' if created else '✓ Réutilisé existant'
        self.stdout.write(self.style.SUCCESS(f'{prefix} : WebhookEndpoint {endpoint.djstripe_uuid}'))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Utilise cette URL dans `stripe listen` :'))
        self.stdout.write(self.style.WARNING(f'  stripe listen --forward-to {full_url}'))
