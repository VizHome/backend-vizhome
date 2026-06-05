"""Tests du catalogue public des plans."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestPlansCatalog:
    URL = "/api/v1/billing/plans"

    def test_plans_listed_unauthenticated(self, api_client: APIClient):
        r = api_client.get(self.URL)
        assert r.status_code == 200
        names = [p["name"] for p in r.data]
        assert "free" in names
        assert "pro" in names
        assert "enterprise" in names

    def test_pro_plan_has_correct_quotas(self, api_client: APIClient):
        r = api_client.get(self.URL)
        pro = next(p for p in r.data if p["name"] == "pro")
        assert pro["price_eur"] == 1900
        assert pro["renders_limit"] == 50
        assert pro["is_billable"] is True

    def test_free_plan_not_billable(self, api_client: APIClient):
        r = api_client.get(self.URL)
        free = next(p for p in r.data if p["name"] == "free")
        assert free["is_billable"] is False
        assert free["price_eur"] == 0
