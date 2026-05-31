"""Tests du tracking des uploads d'images forum (ForumUpload + cleanup)."""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.forum.models import ForumUpload, Reply, Topic
from apps.forum.uploads import extract_used_keys


API = '/api/v1/forum'
# URL publique simulée (cohérent avec MINIO_S3_CUSTOM_DOMAIN+PROTOCOL en dev)
_PUBLIC_PREFIX = 'http://localhost:9000/vizhome-media/'


@pytest.fixture(autouse=True)
def _minio_settings(settings):
    """Force le custom domain MinIO sur tous les tests de ce fichier
    (en config test l'env peut différer)."""
    settings.AWS_S3_CUSTOM_DOMAIN = 'localhost:9000/vizhome-media'
    settings.AWS_S3_URL_PROTOCOL = 'http:'


# ─── Unit : extract_used_keys ────────────────────────────────────────────
class TestExtractUsedKeys:
    def test_empty_html(self):
        assert extract_used_keys('') == set()
        assert extract_used_keys('<p>Texte sans image.</p>') == set()

    def test_extracts_our_minio_keys(self):
        html = (
            '<p>Voici une image :</p>'
            f'<img src="{_PUBLIC_PREFIX}forum/uploads/4/2026/05/abc.png" alt="x">'
        )
        assert extract_used_keys(html) == {'forum/uploads/4/2026/05/abc.png'}

    def test_ignores_external_images(self):
        html = (
            '<img src="https://imgur.com/foo.png">'
            '<img src="https://cdn.example.com/bar.jpg">'
        )
        assert extract_used_keys(html) == set()

    def test_strips_query_params(self):
        html = f'<img src="{_PUBLIC_PREFIX}forum/uploads/x.png?versionId=1">'
        assert extract_used_keys(html) == {'forum/uploads/x.png'}

    def test_multiple_images(self):
        html = (
            f'<img src="{_PUBLIC_PREFIX}forum/uploads/a.png">'
            '<p>Texte</p>'
            f'<img src="{_PUBLIC_PREFIX}forum/uploads/b.jpg" alt="hello">'
            '<img src="https://external.com/c.gif">'
        )
        assert extract_used_keys(html) == {
            'forum/uploads/a.png',
            'forum/uploads/b.jpg',
        }


# ─── Signal : mark used=True quand un Topic / Reply référence un upload ──
@pytest.mark.django_db
class TestSignalMarkUsed:
    def _make_upload(self, user, key='forum/uploads/4/2026/05/abc.png'):
        return ForumUpload.objects.create(
            user=user, key=key,
            url=f'{_PUBLIC_PREFIX}{key}',
            content_type='image/png', size_bytes=1000,
        )

    def test_topic_save_marks_used(self, user, cat_support):
        u = self._make_upload(user)
        assert u.used is False

        Topic.objects.create(
            category=cat_support, author=user,
            title='Voici une capture',
            content=f'<p>Regarde :</p><img src="{u.url}">',
        )
        u.refresh_from_db()
        assert u.used is True
        assert u.first_used_at is not None

    def test_reply_save_marks_used(self, user, topic):
        u = self._make_upload(user, key='forum/uploads/4/2026/05/reply.png')
        assert u.used is False

        Reply.objects.create(
            topic=topic, author=user,
            content=f'<p>Ma réponse :</p><img src="{u.url}">',
        )
        u.refresh_from_db()
        assert u.used is True

    def test_other_user_cannot_validate_my_upload(self, user, other_user, cat_support):
        """Sécurité : un upload ne peut être marked used que si l'AUTEUR
        du Topic/Reply est aussi son uploader."""
        u = self._make_upload(user)
        # Topic créé par other_user qui référence l'upload de `user`
        Topic.objects.create(
            category=cat_support, author=other_user,
            title='Vol d image',
            content=f'<img src="{u.url}">',
        )
        u.refresh_from_db()
        assert u.used is False  # pas marqué — sécurité OK

    def test_topic_without_images_doesnt_touch_uploads(self, user, cat_support):
        u = self._make_upload(user)
        Topic.objects.create(
            category=cat_support, author=user,
            title='Pas d image',
            content='<p>Juste du texte.</p>',
        )
        u.refresh_from_db()
        assert u.used is False

    def test_external_image_doesnt_mark_used(self, user, cat_support):
        u = self._make_upload(user)
        Topic.objects.create(
            category=cat_support, author=user,
            title='Image externe',
            content='<img src="https://imgur.com/cat.jpg">',
        )
        u.refresh_from_db()
        assert u.used is False


# ─── Management command : cleanup_forum_orphan_uploads ───────────────────
@pytest.mark.django_db
class TestCleanupCommand:
    def _make_upload(self, user, *, used=False, age_hours=48):
        u = ForumUpload.objects.create(
            user=user, key=f'forum/uploads/x-{used}-{age_hours}.png',
            url='http://example.com/x.png',
            content_type='image/png', size_bytes=100,
            used=used,
        )
        # Backdate created_at
        ForumUpload.objects.filter(pk=u.pk).update(
            created_at=timezone.now() - timedelta(hours=age_hours),
        )
        u.refresh_from_db()
        return u

    def test_dry_run_deletes_nothing(self, user):
        self._make_upload(user, used=False, age_hours=48)
        with patch('apps.forum.management.commands.cleanup_forum_orphan_uploads.default_storage'):
            call_command('cleanup_forum_orphan_uploads', '--dry-run')
        assert ForumUpload.objects.count() == 1

    def test_keeps_recent_orphans(self, user):
        """Période de grâce de 24h par défaut."""
        self._make_upload(user, used=False, age_hours=1)  # trop récent
        with patch('apps.forum.management.commands.cleanup_forum_orphan_uploads.default_storage'):
            call_command('cleanup_forum_orphan_uploads')
        assert ForumUpload.objects.count() == 1

    def test_keeps_used_even_if_old(self, user):
        """Une fois utilisé, l'upload ne doit JAMAIS être supprimé par
        cette commande (même si très vieux)."""
        self._make_upload(user, used=True, age_hours=1000)
        with patch('apps.forum.management.commands.cleanup_forum_orphan_uploads.default_storage'):
            call_command('cleanup_forum_orphan_uploads')
        assert ForumUpload.objects.count() == 1

    def test_deletes_old_orphans(self, user):
        old_orphan = self._make_upload(user, used=False, age_hours=48)
        with patch(
            'apps.forum.management.commands.cleanup_forum_orphan_uploads.default_storage'
        ) as storage:
            storage.exists.return_value = True
            call_command('cleanup_forum_orphan_uploads')
            storage.delete.assert_called_once_with(old_orphan.key)
        assert ForumUpload.objects.count() == 0

    def test_custom_hours(self, user):
        """--hours 6 → supprime les orphelins > 6h."""
        self._make_upload(user, used=False, age_hours=12)
        with patch('apps.forum.management.commands.cleanup_forum_orphan_uploads.default_storage'):
            call_command('cleanup_forum_orphan_uploads', '--hours', '6')
        assert ForumUpload.objects.count() == 0


# ─── Integration : POST /upload-image crée bien un ForumUpload ───────────
@pytest.mark.django_db
class TestUploadEndpointCreatesRecord:
    def test_upload_creates_forumupload_with_used_false(self, auth_client, user):
        """Sanity check : l'endpoint upload doit créer un ForumUpload."""
        # Petit PNG 1×1 valide
        png_bytes = bytes.fromhex(
            '89504e470d0a1a0a0000000d4948445200000001000000010806000000'
            '1f15c4890000000d49444154789c63f8cfc0000000030001019ec0bf'
            '590000000049454e44ae426082'
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile(
            'pix.png', png_bytes, content_type='image/png',
        )

        r = auth_client.post(
            f'{API}/upload-image',
            data={'file': upload},
            format='multipart',
        )
        assert r.status_code == 201, r.data
        assert ForumUpload.objects.filter(user=user, used=False).count() == 1

    def test_invalid_type_returns_400(self, auth_client):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile(
            'malware.exe', b'MZ\x90', content_type='application/x-msdownload',
        )
        r = auth_client.post(
            f'{API}/upload-image',
            data={'file': upload},
            format='multipart',
        )
        assert r.status_code == 400
        assert r.data['code'] == 'invalid_type'
        assert ForumUpload.objects.count() == 0

    def test_no_file_returns_400(self, auth_client):
        r = auth_client.post(f'{API}/upload-image', data={}, format='multipart')
        assert r.status_code == 400
        assert r.data['code'] == 'no_file'

    def test_requires_auth(self, api_client):
        r = api_client.post(f'{API}/upload-image', data={}, format='multipart')
        assert r.status_code == 401
