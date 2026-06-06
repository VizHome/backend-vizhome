"""Tests pour la commande management `bootstrap` et les healthchecks."""

from __future__ import annotations

from io import StringIO
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset le cache (et donc le verrou Redis) entre tests."""
    cache.clear()
    yield
    cache.clear()


# ─── Tests bootstrap command ─────────────────────────────────────────────────


class TestBootstrapCommand:
    def test_bootstrap_runs_migrate_step(self):
        """`bootstrap --only migrate` appelle bien call_command('migrate')."""
        with mock.patch('apps.core.management.commands.bootstrap.call_command') as mocked:
            call_command('bootstrap', '--only', 'migrate', '--skip-lock')
        mocked.assert_called_with('migrate', interactive=False, verbosity=1)

    def test_bootstrap_skip_stripe_does_not_call_stripe_commands(self):
        """`--skip-stripe` ne lance ni setup_stripe_products ni setup_webhook_endpoint."""
        with mock.patch('apps.core.management.commands.bootstrap.call_command') as mocked:
            call_command(
                'bootstrap',
                '--skip-stripe',
                '--skip-lock',
            )

        called_commands = [args[0] for args, _ in mocked.call_args_list]
        assert 'setup_stripe_products' not in called_commands
        assert 'setup_webhook_endpoint' not in called_commands
        # Mais migrate doit avoir tourné
        assert 'migrate' in called_commands

    @override_settings(STRIPE_TEST_SECRET_KEY='', STRIPE_LIVE_SECRET_KEY='')
    def test_bootstrap_skips_stripe_when_not_configured(self):
        """Si aucune clé Stripe n'est définie, les commandes Stripe sont skip."""
        with mock.patch('apps.core.management.commands.bootstrap.call_command') as mocked:
            call_command('bootstrap', '--skip-lock')

        called_commands = [args[0] for args, _ in mocked.call_args_list]
        assert 'setup_stripe_products' not in called_commands
        assert 'setup_webhook_endpoint' not in called_commands

    def test_bootstrap_lock_acquires_and_releases(self):
        """Le verrou Redis est posé puis relâché en exécution normale."""
        with mock.patch('apps.core.management.commands.bootstrap.call_command'):
            # Vérif post-exécution : le lock a bien été nettoyé
            call_command('bootstrap', '--skip-stripe')

        assert cache.get('vizhome:bootstrap:lock') is None

    def test_bootstrap_returns_early_if_lock_already_held(self):
        """Si un autre process tient déjà le lock, ce replica skip."""
        # Pose un lock détenu par un autre holder
        cache.set('vizhome:bootstrap:lock', 'other-holder', timeout=300)

        out = StringIO()
        with mock.patch('apps.core.management.commands.bootstrap.call_command') as mocked:
            call_command(
                'bootstrap',
                '--wait-for-lock',
                '1',  # 1 sec pour test rapide
                stdout=out,
            )

        # Aucune commande n'a tourné
        assert mocked.call_count == 0
        assert 'déjà en cours' in out.getvalue()

        # Le lock de l'autre holder n'est pas touché
        assert cache.get('vizhome:bootstrap:lock') == 'other-holder'


# ─── Tests healthcheck ───────────────────────────────────────────────────────


@pytest.fixture
def client():
    return APIClient()


class TestHealthcheck:
    def test_liveness_returns_200(self, client):
        url = reverse('health-live')
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {'status': 'ok'}

    def test_readiness_returns_200_when_deps_ok(self, client):
        url = reverse('health-ready')
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['status'] == 'ok'
        assert data['checks']['postgres'] == 'ok'
        assert data['checks']['redis'] == 'ok'

    def test_readiness_returns_503_when_redis_down(self, client):
        """Si la cache lève, /ready retourne 503 + détail."""
        url = reverse('health-ready')
        with mock.patch('django.core.cache.cache.set') as mocked:
            mocked.side_effect = RuntimeError('redis down')
            response = client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data['status'] == 'degraded'
        assert 'error' in data['checks']['redis']
