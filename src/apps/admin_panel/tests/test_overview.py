"""Tests de l'endpoint admin /overview (permissions + shape)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

API = '/api/v1/admin/overview'


@pytest.fixture
def user_normal(db) -> User:
    return User.objects.create_user(
        email='normal@example.com',
        password='Secure!1234',
    )


@pytest.fixture
def user_staff(db) -> User:
    return User.objects.create_user(
        email='admin@example.com',
        password='Secure!1234',
        is_staff=True,
    )


@pytest.fixture
def client_normal(user_normal) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user_normal)
    return c


@pytest.fixture
def client_staff(user_staff) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user_staff)
    return c


@pytest.mark.django_db
class TestPermissions:
    def test_anonymous_gets_401(self):
        r = APIClient().get(API)
        assert r.status_code == 401

    def test_normal_user_gets_403(self, client_normal):
        r = client_normal.get(API)
        assert r.status_code == 403

    def test_staff_user_gets_200(self, client_staff):
        r = client_staff.get(API)
        assert r.status_code == 200


@pytest.mark.django_db
class TestOverviewShape:
    def test_response_has_all_top_level_sections(self, client_staff):
        r = client_staff.get(API)
        assert r.status_code == 200
        expected_keys = {
            'generated_at',
            'users',
            'sessions',
            'renders',
            'projects',
            'storage',
            'billing',
            'forum',
            'system',
        }
        assert set(r.data.keys()) == expected_keys

    def test_users_section_shape(self, client_staff, user_staff):
        r = client_staff.get(API)
        u = r.data['users']
        assert 'total' in u and isinstance(u['total'], int)
        assert 'new_today' in u
        assert 'new_this_week' in u
        assert 'new_this_month' in u
        assert 'by_plan' in u
        assert 'two_factor_enabled' in u
        assert 'staff_count' in u
        assert 'recent' in u
        # Staff user devrait compter
        assert u['total'] >= 1
        assert u['staff_count'] >= 1

    def test_renders_section_shape(self, client_staff):
        r = client_staff.get(API)
        rd = r.data['renders']
        assert 'total' in rd
        assert 'this_month' in rd
        assert 'by_status' in rd
        assert 'by_source' in rd
        assert 'success_rate' in rd
        assert 'recent' in rd

    def test_storage_section_shape(self, client_staff):
        r = client_staff.get(API)
        s = r.data['storage']
        assert 'total_bytes' in s
        assert 'top_users' in s
        assert isinstance(s['top_users'], list)

    def test_billing_section_shape(self, client_staff):
        r = client_staff.get(API)
        b = r.data['billing']
        assert 'paying_users' in b
        assert 'mrr_eur' in b
        assert 'mrr_cents' in b
        assert 'by_plan' in b

    def test_forum_section_shape(self, client_staff):
        r = client_staff.get(API)
        f = r.data['forum']
        assert 'categories' in f
        assert 'topics' in f
        assert 'replies' in f
        assert 'uploads_total' in f
        assert 'uploads_orphan' in f
        assert 'recent_topics' in f

    def test_system_section_reports_integrations(self, client_staff):
        r = client_staff.get(API)
        s = r.data['system']
        for key in (
            'gemini_configured',
            'stripe_configured',
            'google_oauth_configured',
            'github_oauth_configured',
            'minio_configured',
            'otel_configured',
        ):
            assert key in s
            assert isinstance(s[key], bool)


@pytest.mark.django_db
class TestMetricsComputation:
    def test_users_new_today_counted(self, client_staff, user_staff):
        r = client_staff.get(API)
        # Le staff vient d'être créé via la fixture → compté dans new_today
        assert r.data['users']['new_today'] >= 1

    def test_users_by_plan_distribution(self, client_staff):
        # Crée 3 free + 2 pro
        for i in range(3):
            User.objects.create_user(
                email=f'free{i}@example.com',
                password='Pass!1234',
                plan='free',
            )
        for i in range(2):
            User.objects.create_user(
                email=f'pro{i}@example.com',
                password='Pass!1234',
                plan='pro',
            )
        r = client_staff.get(API)
        by_plan = r.data['users']['by_plan']
        assert by_plan.get('free', 0) >= 3
        assert by_plan.get('pro', 0) == 2

    def test_billing_mrr_from_paying_users(self, client_staff):
        # 2 users pro (19€ chacun) → mrr_eur = 38
        for i in range(2):
            User.objects.create_user(
                email=f'mrr-pro-{i}@example.com',
                password='Pass!1234',
                plan='pro',
            )
        r = client_staff.get(API)
        assert r.data['billing']['paying_users'] >= 2
        # Pro = 1900 cents → mrr_cents incrémenté d'au moins 3800
        assert r.data['billing']['mrr_cents'] >= 3800
