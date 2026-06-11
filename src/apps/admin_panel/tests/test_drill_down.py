"""Tests des endpoints drill-down admin (users list + detail, renders list)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

API_USERS = '/api/v1/admin/users'
API_RENDERS = '/api/v1/admin/renders'


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


# ─── /admin/users (list) ─────────────────────────────────────────────────
@pytest.mark.django_db
class TestUsersList:
    def test_requires_staff(self, client_normal):
        r = client_normal.get(API_USERS)
        assert r.status_code == 403

    def test_anonymous_401(self):
        r = APIClient().get(API_USERS)
        assert r.status_code == 401

    def test_list_paginated(self, client_staff, user_staff):
        r = client_staff.get(API_USERS)
        assert r.status_code == 200
        assert 'count' in r.data
        assert 'results' in r.data
        # Au moins le staff user
        assert r.data['count'] >= 1

    def test_filter_by_plan(self, client_staff):
        User.objects.create_user(
            email='pro1@example.com',
            password='Pass!1234',
            plan='pro',
        )
        r = client_staff.get(f'{API_USERS}?plan=pro')
        assert all(u['plan'] == 'pro' for u in r.data['results'])

    def test_filter_by_is_staff(self, client_staff):
        r = client_staff.get(f'{API_USERS}?is_staff=true')
        assert all(u['is_staff'] for u in r.data['results'])

    def test_search_by_email(self, client_staff):
        User.objects.create_user(
            email='john.doe@searchtest.com',
            password='Pass!1234',
        )
        r = client_staff.get(f'{API_USERS}?search=searchtest')
        assert r.data['count'] >= 1
        assert any('searchtest' in u['email'] for u in r.data['results'])


# ─── /admin/users/{id} (detail + PATCH ban/unban) ────────────────────────
@pytest.mark.django_db
class TestUserDetail:
    def test_staff_can_get_user(self, client_staff, user_normal):
        r = client_staff.get(f'{API_USERS}/{user_normal.id}')
        assert r.status_code == 200
        assert r.data['email'] == user_normal.email
        # Champs stats inclus
        assert 'storage_used_bytes' in r.data
        assert 'renders_this_month' in r.data

    def test_staff_can_ban_user(self, client_staff, user_normal):
        assert user_normal.is_active is True
        r = client_staff.patch(
            f'{API_USERS}/{user_normal.id}',
            {'is_active': False},
            format='json',
        )
        assert r.status_code == 200
        user_normal.refresh_from_db()
        assert user_normal.is_active is False

    def test_staff_can_promote_other(self, client_staff, user_normal):
        r = client_staff.patch(
            f'{API_USERS}/{user_normal.id}',
            {'is_staff': True},
            format='json',
        )
        assert r.status_code == 200
        user_normal.refresh_from_db()
        assert user_normal.is_staff is True

    def test_cannot_self_demote_staff(self, client_staff, user_staff):
        r = client_staff.patch(
            f'{API_USERS}/{user_staff.id}',
            {'is_staff': False},
            format='json',
        )
        assert r.status_code == 400
        assert r.data['code'] == 'self_demotion_forbidden'

    def test_cannot_self_deactivate(self, client_staff, user_staff):
        r = client_staff.patch(
            f'{API_USERS}/{user_staff.id}',
            {'is_active': False},
            format='json',
        )
        assert r.status_code == 400
        assert r.data['code'] == 'self_deactivation_forbidden'

    def test_normal_user_cannot_patch(self, client_normal, user_staff):
        r = client_normal.patch(
            f'{API_USERS}/{user_staff.id}',
            {'is_active': False},
            format='json',
        )
        assert r.status_code == 403


# ─── /admin/renders (list) ───────────────────────────────────────────────
@pytest.mark.django_db
class TestRendersList:
    def test_requires_staff(self, client_normal):
        r = client_normal.get(API_RENDERS)
        assert r.status_code == 403

    def test_list_empty_ok(self, client_staff):
        r = client_staff.get(API_RENDERS)
        assert r.status_code == 200
        assert 'count' in r.data

    def test_returns_user_email_with_render(self, client_staff, user_normal):
        from apps.renders.models import Render

        Render.objects.create(
            user=user_normal,
            source=Render.Source.PROMPT,
            output_type=Render.OutputType.IMAGE_2D,
            prompt='test',
            provider='gemini',
        )
        r = client_staff.get(API_RENDERS)
        assert r.data['count'] >= 1
        first = r.data['results'][0]
        assert first['user_email'] == user_normal.email
