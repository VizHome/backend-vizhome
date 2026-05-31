"""Tests de la permission IsAuthorWithinTimeWindowOrStaff."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.forum.models import Reply, Topic


API = '/api/v1/forum'


@pytest.mark.django_db
class TestEditWindowTopic:
    def test_author_can_edit_immediately(self, auth_client, topic):
        r = auth_client.patch(
            f'{API}/topics/{topic.id}',
            {'content': 'Édité dans la minute.'},
            format='json',
        )
        assert r.status_code == 200, r.data
        assert r.data['content'] == 'Édité dans la minute.'

    def test_author_cannot_edit_after_window(self, auth_client, topic):
        # Backdate le topic à 16 min en arrière → hors fenêtre (15 min)
        Topic.objects.filter(pk=topic.pk).update(
            created_at=timezone.now() - timedelta(minutes=16)
        )
        r = auth_client.patch(
            f'{API}/topics/{topic.id}',
            {'content': 'Édition tardive interdite.'},
            format='json',
        )
        assert r.status_code == 403
        # Le message d'erreur doit mentionner la fenêtre
        assert 'fenêtre' in str(r.data).lower() or 'window' in str(r.data).lower()

    def test_staff_can_edit_anytime(self, staff_client, topic):
        # Même vieux topic : staff peut éditer
        Topic.objects.filter(pk=topic.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        r = staff_client.patch(
            f'{API}/topics/{topic.id}',
            {'content': 'Modéré par staff.'},
            format='json',
        )
        assert r.status_code == 200

    def test_other_user_never_can_edit(self, api_client, topic, other_user):
        api_client.force_authenticate(user=other_user)
        r = api_client.patch(
            f'{API}/topics/{topic.id}',
            {'content': 'Hack attempt.'},
            format='json',
        )
        assert r.status_code == 403


@pytest.mark.django_db
class TestEditWindowReply:
    def test_author_can_edit_reply_immediately(self, auth_client, user, topic):
        reply = Reply.objects.create(
            topic=topic, author=user, content='Réponse initiale.',
        )
        r = auth_client.patch(
            f'{API}/replies/{reply.id}',
            {'content': 'Réponse éditée.'},
            format='json',
        )
        assert r.status_code == 200

    def test_author_cannot_edit_reply_after_window(self, auth_client, user, topic):
        reply = Reply.objects.create(
            topic=topic, author=user, content='Vieille réponse.',
        )
        # Hors fenêtre
        Reply.objects.filter(pk=reply.pk).update(
            created_at=timezone.now() - timedelta(minutes=20)
        )
        r = auth_client.patch(
            f'{API}/replies/{reply.id}',
            {'content': 'Trop tard.'},
            format='json',
        )
        assert r.status_code == 403

    def test_author_can_delete_reply_within_window(self, auth_client, user, topic):
        reply = Reply.objects.create(
            topic=topic, author=user, content='Va être supprimée.',
        )
        r = auth_client.delete(f'{API}/replies/{reply.id}')
        assert r.status_code == 204

    def test_author_cannot_delete_reply_after_window(self, auth_client, user, topic):
        reply = Reply.objects.create(
            topic=topic, author=user, content='Trop vieille.',
        )
        Reply.objects.filter(pk=reply.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        r = auth_client.delete(f'{API}/replies/{reply.id}')
        assert r.status_code == 403
