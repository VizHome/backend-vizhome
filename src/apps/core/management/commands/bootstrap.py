"""Bootstrap idempotent du backend — à exécuter au démarrage de l'API.

Orchestration "zéro commande manuelle" : peut être lancé en dev ou en prod
sans devoir penser à `migrate`, `collectstatic`, etc.

Étapes (toutes idempotentes) :
    1. migrate           : applique les migrations en attente
    2. collectstatic     : agrège les fichiers statiques (si STATIC_ROOT défini)
    3. compilemessages   : compile les .po → .mo (si dossier locale présent)
    4. seed_forum_categories : crée les catégories forum si absentes
    5. setup_stripe_products : sync les Products/Prices Stripe (si configuré)
    6. setup_webhook_endpoint : crée/récupère le WebhookEndpoint dj-stripe

Multi-replica : verrou Redis (`vizhome:bootstrap:lock`) avec TTL 5 min pour
éviter que plusieurs containers parallèles ne tentent les migrations en même
temps (risque de deadlock Postgres + erreurs de duplication).

Usage :
    python manage.py bootstrap                 # tout exécuter
    python manage.py bootstrap --skip-stripe   # skip Stripe (CI sans secrets)
    python manage.py bootstrap --only migrate  # ne fait que migrate
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

LOCK_KEY = 'vizhome:bootstrap:lock'
LOCK_TTL = 300  # 5 min — large couverture pour collectstatic + migrations
LOCK_HOLDER_VALUE = (
    f'pid:{os.getpid()}:host:{os.uname().nodename if hasattr(os, "uname") else "win"}'
)


class Command(BaseCommand):
    help = (
        'Bootstrap idempotent du backend — migrate + collectstatic + Stripe + i18n. '
        'Sûr en multi-replica grâce à un verrou Redis.'
    )

    AVAILABLE_STEPS = (
        'migrate',
        'collectstatic',
        'compilemessages',
        'seed_forum',
        'setup_stripe',
        'setup_webhook',
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--skip-stripe',
            action='store_true',
            help='Skip les commandes Stripe (utile en CI ou si Stripe non configuré).',
        )
        parser.add_argument(
            '--skip-lock',
            action='store_true',
            help='Skip le verrou Redis (utile pour dev local single-process).',
        )
        parser.add_argument(
            '--only',
            choices=self.AVAILABLE_STEPS,
            help="N'exécute qu'une seule étape.",
        )
        parser.add_argument(
            '--wait-for-lock',
            type=int,
            default=60,
            help="Secondes max d'attente du verrou si déjà tenu (défaut 60).",
        )

    # ────────────────────────────────────────────────────────────────────
    def handle(self, *args, **opts: Any) -> None:
        only = opts.get('only')
        skip_stripe = opts.get('skip_stripe', False)
        skip_lock = opts.get('skip_lock', False)
        wait_for_lock = opts.get('wait_for_lock', 60)

        if only:
            self._log_step(f'Mode --only={only} : exécution unique')
            self._run_step(only, skip_stripe=False)
            return

        if not skip_lock and not self._acquire_lock(wait_seconds=wait_for_lock):
            self.stdout.write(
                self.style.WARNING(
                    'Bootstrap déjà en cours sur un autre replica. '
                    'Skip et continue (ce replica fera juste exec du CMD).'
                )
            )
            return

        try:
            self._run_step('migrate')
            self._run_step('collectstatic')
            self._run_step('compilemessages')
            self._run_step('seed_forum')
            if not skip_stripe:
                self._run_step('setup_stripe')
                self._run_step('setup_webhook')
            else:
                self._log_step('Stripe skip (--skip-stripe).')
        finally:
            if not skip_lock:
                self._release_lock()

        self.stdout.write(self.style.SUCCESS('✓ Bootstrap terminé'))

    # ────────────────────────────────────────────────────────────────────
    # Verrou Redis (via Django cache)
    # ────────────────────────────────────────────────────────────────────
    def _acquire_lock(self, wait_seconds: int) -> bool:
        """Tente de poser le verrou avec attente max `wait_seconds`.

        Retourne True si on a le verrou, False si autre replica le tient
        après timeout.
        """
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            # `cache.add` ne pose que si la clé n'existe pas (atomic SET NX)
            if cache.add(LOCK_KEY, LOCK_HOLDER_VALUE, timeout=LOCK_TTL):
                self._log_step(f'Verrou acquis ({LOCK_HOLDER_VALUE}).')
                return True
            self.stdout.write('  ⏳ Verrou détenu par un autre replica, attente 2s…')
            time.sleep(2)
        return False

    def _release_lock(self) -> None:
        # Ne supprime que si on est bien le détenteur (évite de relâcher
        # le verrou d'un autre process si on a dépassé le TTL).
        holder = cache.get(LOCK_KEY)
        if holder == LOCK_HOLDER_VALUE:
            cache.delete(LOCK_KEY)
            self._log_step('Verrou relâché.')
        else:
            logger.warning(
                'Lock holder mismatch on release: expected %s got %s',
                LOCK_HOLDER_VALUE,
                holder,
            )

    # ────────────────────────────────────────────────────────────────────
    # Étapes individuelles
    # ────────────────────────────────────────────────────────────────────
    def _run_step(self, name: str, *, skip_stripe: bool = False) -> None:
        handler = getattr(self, f'_step_{name}')
        self._log_step(f'▶ {name}')
        try:
            handler()
            self.stdout.write(self.style.SUCCESS(f'  ✓ {name} OK'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ {name} ÉCHEC : {e}'))
            logger.exception('bootstrap step %s failed', name)
            raise

    def _step_migrate(self) -> None:
        call_command('migrate', interactive=False, verbosity=1)

    def _step_collectstatic(self) -> None:
        if not getattr(settings, 'STATIC_ROOT', None):
            self.stdout.write('  • STATIC_ROOT non défini, skip')
            return
        call_command('collectstatic', interactive=False, verbosity=0)

    def _step_compilemessages(self) -> None:
        # Skip si pas de dossier locale (typique en CI sans i18n)
        from pathlib import Path

        locale_dir = Path(settings.BASE_DIR) / 'locale'
        if not locale_dir.exists():
            self.stdout.write('  • Pas de dossier locale/, skip')
            return
        try:
            call_command('compilemessages', verbosity=0)
        except Exception as e:
            # Pas bloquant : si gettext n'est pas installé sur l'image, on
            # log et continue (impact = traductions absentes mais l'API up).
            self.stdout.write(self.style.WARNING(f'  • compilemessages non bloquant : {e}'))

    def _step_seed_forum(self) -> None:
        # Commande custom qui crée les catégories forum si absentes
        try:
            call_command('seed_forum_categories', verbosity=0)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  • seed_forum_categories non bloquant : {e}'))

    def _step_setup_stripe(self) -> None:
        if not self._stripe_configured():
            self.stdout.write('  • Stripe non configuré (STRIPE_*_SECRET_KEY absent), skip')
            return
        call_command('setup_stripe_products', verbosity=1)

    def _step_setup_webhook(self) -> None:
        if not self._stripe_configured():
            self.stdout.write('  • Stripe non configuré, skip')
            return
        call_command('setup_webhook_endpoint', verbosity=1)

    # ────────────────────────────────────────────────────────────────────
    def _stripe_configured(self) -> bool:
        return bool(
            getattr(settings, 'STRIPE_TEST_SECRET_KEY', '')
            or getattr(settings, 'STRIPE_LIVE_SECRET_KEY', '')
        )

    def _log_step(self, msg: str) -> None:
        self.stdout.write(self.style.HTTP_INFO(msg))
