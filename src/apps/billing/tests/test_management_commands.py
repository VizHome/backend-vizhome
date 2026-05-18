"""Tests des management commands billing + accounts."""
from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import UserStats


@pytest.mark.django_db
class TestSetupStripeProducts:
    def test_fails_if_stripe_not_configured(self):
        with pytest.raises(CommandError, match='Stripe API key absente'):
            call_command('setup_stripe_products', stdout=StringIO())

    @patch('apps.billing.management.commands.setup_stripe_products.get_stripe_client')
    def test_creates_products_and_prices(self, mock_get_stripe):
        mock_stripe = MagicMock()
        # Pas de Product existant pour aucun plan
        mock_stripe.Product.search.return_value = MagicMock(data=[])
        # Pas de Price existante non plus
        mock_stripe.Price.list.return_value = MagicMock(data=[])
        # Mock des créations
        mock_stripe.Product.create.return_value = MagicMock(id='prod_123')
        mock_stripe.Price.create.return_value = MagicMock(id='price_123')
        mock_get_stripe.return_value = mock_stripe

        out = StringIO()
        call_command('setup_stripe_products', stdout=out)

        # 2 plans billables (pro + enterprise) → 2 Products + 2 Prices créés
        assert mock_stripe.Product.create.call_count == 2
        assert mock_stripe.Price.create.call_count == 2

    @patch('apps.billing.management.commands.setup_stripe_products.get_stripe_client')
    def test_dry_run_no_api_calls(self, mock_get_stripe):
        mock_get_stripe.return_value = MagicMock()
        out = StringIO()
        call_command('setup_stripe_products', '--dry-run', stdout=out)

        mock_get_stripe.return_value.Product.create.assert_not_called()
        mock_get_stripe.return_value.Price.create.assert_not_called()


@pytest.mark.django_db
class TestResetMonthlyCounters:
    def test_resets_all_users(self):
        from apps.accounts.models import User
        u1 = User.objects.create_user(email='a@a.fr', password='x')
        u2 = User.objects.create_user(email='b@b.fr', password='x')
        UserStats.objects.filter(user=u1).update(renders_this_month=42)
        UserStats.objects.filter(user=u2).update(renders_this_month=7)

        call_command('reset_monthly_counters', stdout=StringIO())

        u1.stats.refresh_from_db()
        u2.stats.refresh_from_db()
        assert u1.stats.renders_this_month == 0
        assert u2.stats.renders_this_month == 0
