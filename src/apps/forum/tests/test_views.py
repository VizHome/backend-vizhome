"""Tests des endpoints DRF du forum."""

from __future__ import annotations

import pytest

from apps.forum.models import Category, Reply, Topic

API = "/api/v1/forum"


# ─── Categories ────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestCategories:
    def test_list_public(self, api_client, cat_support, cat_annonces):
        r = api_client.get(f"{API}/categories")
        assert r.status_code == 200
        # Pas paginé (override pagination_class = None)
        assert isinstance(r.data, list)
        assert len(r.data) == 2
        # Triées par order, support (1) avant annonces (2)
        assert r.data[0]["slug"] == "support"

    def test_detail_by_slug(self, api_client, cat_support):
        r = api_client.get(f"{API}/categories/support")
        assert r.status_code == 200
        assert r.data["slug"] == "support"


# ─── Topics ────────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestTopics:
    def test_list_paginated(self, api_client, topic):
        r = api_client.get(f"{API}/topics")
        assert r.status_code == 200
        assert r.data["count"] == 1
        assert r.data["results"][0]["title"] == topic.title

    def test_filter_by_category(self, api_client, topic, cat_annonces):
        r = api_client.get(f"{API}/topics?category=annonces")
        assert r.status_code == 200
        assert r.data["count"] == 0  # le topic est dans support, pas annonces

    def test_search(self, api_client, topic):
        r = api_client.get(f"{API}/topics?search=GLB")
        assert r.status_code == 200
        assert r.data["count"] == 1

    def test_create_requires_auth(self, api_client, cat_support):
        r = api_client.post(
            f"{API}/topics",
            {
                "category": cat_support.id,
                "title": "Hello world",
                "content": "Bonjour la communauté.",
            },
            format="json",
        )
        assert r.status_code == 401

    def test_create_ok(self, auth_client, cat_support):
        r = auth_client.post(
            f"{API}/topics",
            {
                "category": cat_support.id,
                "title": "Hello world",
                "content": "Bonjour la communauté.",
            },
            format="json",
        )
        assert r.status_code == 201, r.data
        # Slug regenéré avec l'id en préfixe
        assert r.data["slug"].startswith(f"{r.data['id']}-")
        # Compteur category mis à jour via signal
        cat_support.refresh_from_db()
        assert cat_support.topics_count == 1

    def test_create_in_admin_only_forbidden_for_user(self, auth_client, cat_annonces):
        r = auth_client.post(
            f"{API}/topics",
            {
                "category": cat_annonces.id,
                "title": "Tentative",
                "content": "Devrait être rejeté.",
            },
            format="json",
        )
        assert r.status_code == 403
        assert r.data["code"] == "category_locked"

    def test_create_in_admin_only_allowed_for_staff(self, staff_client, cat_annonces):
        r = staff_client.post(
            f"{API}/topics",
            {
                "category": cat_annonces.id,
                "title": "Release v2.0",
                "content": "Voici les nouveautés.",
            },
            format="json",
        )
        assert r.status_code == 201

    def test_detail_increments_views(self, api_client, topic):
        assert topic.views_count == 0
        r = api_client.get(f"{API}/topics/{topic.id}")
        assert r.status_code == 200
        topic.refresh_from_db()
        assert topic.views_count == 1

    def test_owner_can_patch(self, auth_client, topic):
        r = auth_client.patch(
            f"{API}/topics/{topic.id}",
            {
                "content": "Contenu mis à jour.",
            },
            format="json",
        )
        assert r.status_code == 200
        assert r.data["content"] == "Contenu mis à jour."

    def test_other_user_cannot_patch(self, api_client, topic, other_user):
        api_client.force_authenticate(user=other_user)
        r = api_client.patch(
            f"{API}/topics/{topic.id}",
            {
                "content": "Hack attempt.",
            },
            format="json",
        )
        assert r.status_code == 403

    def test_staff_can_patch_any(self, staff_client, topic):
        r = staff_client.patch(
            f"{API}/topics/{topic.id}",
            {
                "content": "Modéré par staff.",
            },
            format="json",
        )
        assert r.status_code == 200

    def test_owner_can_delete(self, auth_client, topic, cat_support):
        r = auth_client.delete(f"{API}/topics/{topic.id}")
        assert r.status_code == 204
        # Compteur cat décrémenté via signal
        cat_support.refresh_from_db()
        assert cat_support.topics_count == 0


# ─── Replies ───────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestReplies:
    def test_list_public(self, api_client, topic, user):
        Reply.objects.create(topic=topic, author=user, content="First reply.")
        r = api_client.get(f"{API}/topics/{topic.id}/replies")
        assert r.status_code == 200
        assert r.data["count"] == 1

    def test_create_requires_auth(self, api_client, topic):
        r = api_client.post(
            f"{API}/topics/{topic.id}/replies",
            {
                "content": "Réponse.",
            },
            format="json",
        )
        assert r.status_code == 401

    def test_create_ok_updates_counters(self, auth_client, topic):
        r = auth_client.post(
            f"{API}/topics/{topic.id}/replies",
            {
                "content": "Ma réponse.",
            },
            format="json",
        )
        assert r.status_code == 201, r.data
        topic.refresh_from_db()
        assert topic.replies_count == 1
        assert topic.last_reply_at is not None

    def test_locked_topic_rejects_reply(self, auth_client, topic):
        topic.is_locked = True
        topic.save()
        r = auth_client.post(
            f"{API}/topics/{topic.id}/replies",
            {
                "content": "Test.",
            },
            format="json",
        )
        assert r.status_code == 403
        assert r.data["code"] == "topic_locked"

    def test_owner_can_delete_own_reply(self, auth_client, topic, user):
        reply = Reply.objects.create(topic=topic, author=user, content="Mine.")
        r = auth_client.delete(f"{API}/replies/{reply.id}")
        assert r.status_code == 204
        topic.refresh_from_db()
        assert topic.replies_count == 0

    def test_other_user_cannot_delete_reply(self, api_client, topic, user, other_user):
        reply = Reply.objects.create(topic=topic, author=user, content="Not yours.")
        api_client.force_authenticate(user=other_user)
        r = api_client.delete(f"{API}/replies/{reply.id}")
        assert r.status_code == 403


# ─── Cascade ───────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestCascade:
    def test_delete_topic_cascades_replies(self, auth_client, topic, user):
        Reply.objects.create(topic=topic, author=user, content="To be deleted.")
        topic.delete()
        assert Reply.objects.count() == 0

    def test_delete_category_cascades_topics(self, db, cat_support, topic):
        cat_support.delete()
        assert Topic.objects.count() == 0
