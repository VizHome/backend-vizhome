"""Tests endpoints subscription : status, checkout, cancel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status


@pytest.mark.django_db
class TestSubscriptionStatus:
    URL = "/api/v1/me/subscription"

    def test_get_subscription_no_stripe_configured(self, auth_client, user):
        # Sans clé Stripe configurée → renvoie quand même un état (basé user.plan)
        r = auth_client.get(self.URL)
        assert r.status_code == 200
        assert r.data["plan"] == "free"
        assert r.data["has_subscription"] is False

    def test_requires_auth(self, api_client):
        r = api_client.get(self.URL)
        assert r.status_code == 401


@pytest.mark.django_db
class TestCheckout:
    URL = "/api/v1/me/subscription/checkout"

    def test_checkout_without_stripe_returns_503(self, auth_client):
        # Pas de STRIPE_TEST_SECRET_KEY dans test settings
        r = auth_client.post(self.URL, {"plan": "pro"}, format="json")
        assert r.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert r.data["code"] == "stripe_unavailable"

    @patch("apps.billing.views.is_configured", return_value=True)
    @patch("apps.billing.views.get_stripe_client")
    @patch("apps.billing.views._get_or_create_customer")
    def test_checkout_creates_session(
        self, mock_customer, mock_get_stripe, _mock_cfg, auth_client
    ):
        mock_customer.return_value = MagicMock(id="cus_test123")
        mock_stripe = MagicMock()
        mock_stripe.Price.list.return_value = MagicMock(
            data=[MagicMock(id="price_test123")]
        )
        mock_stripe.checkout.Session.create.return_value = MagicMock(
            id="cs_test_abc",
            url="https://checkout.stripe.com/c/abc",
        )
        mock_get_stripe.return_value = mock_stripe

        r = auth_client.post(self.URL, {"plan": "pro"}, format="json")
        assert r.status_code == 200
        assert r.data["checkout_url"] == "https://checkout.stripe.com/c/abc"
        assert r.data["session_id"] == "cs_test_abc"

        # Vérifie que la création s'est faite avec les bons params
        call_kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["line_items"] == [{"price": "price_test123", "quantity": 1}]

    @patch("apps.billing.views.is_configured", return_value=True)
    @patch("apps.billing.views.get_stripe_client")
    def test_checkout_fails_if_price_not_found(
        self, mock_get_stripe, _cfg, auth_client
    ):
        mock_stripe = MagicMock()
        mock_stripe.Price.list.return_value = MagicMock(data=[])
        mock_get_stripe.return_value = mock_stripe

        r = auth_client.post(self.URL, {"plan": "pro"}, format="json")
        assert r.status_code == 400
        assert "setup_stripe_products" in r.data["detail"]

    @patch("apps.billing.views.is_configured", return_value=True)
    def test_invalid_plan_rejected(self, _cfg, auth_client):
        r = auth_client.post(self.URL, {"plan": "invalid"}, format="json")
        assert r.status_code == 400


@pytest.mark.django_db
class TestCancel:
    URL = "/api/v1/me/subscription/cancel"

    def test_cancel_without_stripe(self, auth_client):
        r = auth_client.post(self.URL)
        assert r.status_code == 503
