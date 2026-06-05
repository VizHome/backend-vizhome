"""Tests des webhook handlers : application du plan suivant la subscription Stripe."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.billing.handlers import _apply_plan_to_user


@pytest.mark.django_db
class TestApplyPlan:
    def test_upgrade_to_pro_adjusts_quotas(self, user):
        _apply_plan_to_user(user, "pro")
        user.refresh_from_db()
        user.stats.refresh_from_db()
        assert user.plan == "pro"
        assert user.stats.renders_limit == 50
        assert user.stats.storage_limit_bytes == 5 * 1024**3

    def test_downgrade_to_free_lowers_quotas(self, user):
        _apply_plan_to_user(user, "pro")
        _apply_plan_to_user(user, "free")
        user.refresh_from_db()
        user.stats.refresh_from_db()
        assert user.plan == "free"
        assert user.stats.renders_limit == 5
        assert user.stats.storage_limit_bytes == 1 * 1024**3

    def test_upgrade_to_enterprise(self, user):
        _apply_plan_to_user(user, "enterprise")
        user.refresh_from_db()
        user.stats.refresh_from_db()
        assert user.plan == "enterprise"
        assert user.stats.renders_limit == 9999


@pytest.mark.django_db
class TestSubscriptionHandlers:
    """Tests du handler customer.subscription.created/updated."""

    def _make_event(self, sub_id: str) -> MagicMock:
        event = MagicMock()
        event.data = {"object": {"id": sub_id}}
        return event

    def _make_subscription(
        self, user, lookup_key="vizhome_pro_monthly", status="active"
    ):
        sub = MagicMock()
        sub.status = status
        item = MagicMock()
        item.price.lookup_key = lookup_key
        sub.items.first.return_value = item
        sub.customer.subscriber_id = user.pk
        return sub

    @patch("apps.billing.handlers.dj_models")
    def test_subscription_created_applies_plan(self, mock_dj, user):
        from apps.billing.handlers import on_subscription_change

        sub = self._make_subscription(user)
        mock_dj.Subscription.objects.get.return_value = sub

        on_subscription_change(self._make_event("sub_123"))

        user.refresh_from_db()
        assert user.plan == "pro"

    @patch("apps.billing.handlers.dj_models")
    def test_subscription_inactive_does_not_change_plan(self, mock_dj, user):
        from apps.billing.handlers import on_subscription_change

        sub = self._make_subscription(user, status="past_due")
        mock_dj.Subscription.objects.get.return_value = sub

        original_plan = user.plan
        on_subscription_change(self._make_event("sub_456"))

        user.refresh_from_db()
        assert user.plan == original_plan
