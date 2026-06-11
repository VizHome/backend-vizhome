"""Vues DRF du forum."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.core.files.storage import default_storage
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import ForumWriteThrottle

from .models import Category, ForumUpload, Reply, Topic
from .permissions import (
    IsAuthorWithinTimeWindowOrStaff,
    IsNotForumBanned,
)
from .serializers import (
    CategorySerializer,
    ReplyCreateSerializer,
    ReplySerializer,
    TopicCreateSerializer,
    TopicDetailSerializer,
    TopicListSerializer,
)


# ─── Categories (lecture publique uniquement) ──────────────────────────────
class CategoryListView(generics.ListAPIView):
    """GET /forum/categories — liste publique des catégories."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = CategorySerializer
    pagination_class = None  # peu de catégories, pas besoin de pagination

    def get_queryset(self):
        return Category.objects.all().order_by('order', 'name')


class CategoryDetailView(generics.RetrieveAPIView):
    """GET /forum/categories/{slug} — détail d'une catégorie."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = CategorySerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Category.objects.all()


# ─── Topics ────────────────────────────────────────────────────────────────
class TopicListCreateView(generics.ListCreateAPIView):
    """GET /forum/topics — liste paginée (publique).
    POST /forum/topics — crée (auth requis).

    Query params :
    - ?category=<slug>  : filtre par catégorie
    - ?search=<q>       : recherche dans title (icontains)
    - ?ordering=...     : `created_at`, `-created_at`, `-last_reply_at`, etc.
    """

    def get_throttles(self):
        """Anti-flood : 30 topics/min/user max sur POST."""
        if self.request.method == 'POST':
            return [ForumWriteThrottle()]
        return super().get_throttles()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsNotForumBanned()]
        return [AllowAny()]

    def get_authenticators(self):
        # GET public — pas d'auth → évite les 401 sur tokens expirés
        if self.request.method == 'GET':
            return []
        return super().get_authenticators()

    def get_serializer_class(self):
        return TopicCreateSerializer if self.request.method == 'POST' else TopicListSerializer

    def get_queryset(self):
        qs = Topic.objects.select_related('category', 'author').all()

        category_slug = self.request.query_params.get('category')
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(title__icontains=search.strip())

        ordering = self.request.query_params.get('ordering')
        allowed = {
            'created_at',
            '-created_at',
            'last_reply_at',
            '-last_reply_at',
            'replies_count',
            '-replies_count',
            'views_count',
            '-views_count',
        }
        if ordering in allowed:
            qs = qs.order_by(ordering)
        else:
            # Par défaut : pinned d'abord, puis dernière activité
            qs = qs.order_by('-is_pinned', '-last_reply_at', '-created_at')

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Empêche les non-staff de poster dans les catégories is_admin_only
        category = serializer.validated_data['category']
        if category.is_admin_only and not request.user.is_staff:
            return Response(
                {
                    'detail': f'Seul le staff peut poster dans « {category.name} ».',
                    'code': 'category_locked',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        topic = serializer.save(author=request.user)
        # Re-slug avec l'id pour URLs uniques (`12-comment-importer-glb`)
        topic.slug = f'{topic.pk}-{topic.slug[:200]}'
        topic.save(update_fields=['slug'])

        output = TopicDetailSerializer(topic, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class TopicDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /forum/topics/{id}.

    Édition limitée à 15 min pour l'auteur (staff toujours OK).
    """

    permission_classes = [IsAuthorWithinTimeWindowOrStaff]
    serializer_class = TopicDetailSerializer
    EDIT_WINDOW_MINUTES = 15

    def get_authenticators(self):
        if self.request.method == 'GET':
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsAuthorWithinTimeWindowOrStaff()]

    def get_queryset(self):
        return Topic.objects.select_related('category', 'author').all()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Incrémente le compteur de vues (atomic, anti-race)
        Topic.objects.filter(pk=instance.pk).update(views_count=F('views_count') + 1)
        instance.refresh_from_db(fields=['views_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


# ─── Replies ───────────────────────────────────────────────────────────────
class ReplyListCreateView(generics.ListCreateAPIView):
    """GET /forum/topics/{topic_id}/replies — liste paginée.
    POST /forum/topics/{topic_id}/replies — crée (auth).
    """

    serializer_class = ReplySerializer

    def get_throttles(self):
        """Anti-flood replies : partage le scope `forum-write` avec les topics."""
        if self.request.method == 'POST':
            return [ForumWriteThrottle()]
        return super().get_throttles()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsNotForumBanned()]
        return [AllowAny()]

    def get_authenticators(self):
        if self.request.method == 'GET':
            return []
        return super().get_authenticators()

    def get_serializer_class(self):
        return ReplyCreateSerializer if self.request.method == 'POST' else ReplySerializer

    def get_queryset(self):
        return (
            Reply.objects.filter(topic_id=self.kwargs['topic_id'])
            .select_related('author')
            .order_by('created_at')
        )

    def create(self, request, *args, **kwargs):
        topic = get_object_or_404(Topic, pk=self.kwargs['topic_id'])
        if topic.is_locked:
            return Response(
                {'detail': 'Ce topic est verrouillé.', 'code': 'topic_locked'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = serializer.save(author=request.user, topic=topic)

        output = ReplySerializer(reply, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class ReplyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """PATCH/DELETE /forum/replies/{id} — édition limitée dans le temps.

    L'auteur peut éditer sa réponse dans les 15 min qui suivent. Passé
    ce délai, seul le staff peut éditer.
    """

    permission_classes = [IsAuthenticated, IsAuthorWithinTimeWindowOrStaff]
    serializer_class = ReplySerializer
    EDIT_WINDOW_MINUTES = 15

    def get_queryset(self):
        return Reply.objects.select_related('author', 'topic').all()


# ─── Actions modération (staff ou owner du topic selon le cas) ─────────────
class TopicTogglePinView(APIView):
    """POST /forum/topics/{id}/toggle-pin — épingle/désépingle (staff only)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int, *args, **kwargs):
        if not request.user.is_staff:
            return Response(
                {'detail': 'Réservé au staff.', 'code': 'forbidden'},
                status=status.HTTP_403_FORBIDDEN,
            )
        topic = get_object_or_404(Topic, pk=pk)
        topic.is_pinned = not topic.is_pinned
        topic.save(update_fields=['is_pinned'])
        # Audit log staff action
        from apps.admin_panel.audit import log_admin_action
        from apps.admin_panel.models import AdminAuditLog

        log_admin_action(
            request,
            (
                AdminAuditLog.Action.TOPIC_PIN
                if topic.is_pinned
                else AdminAuditLog.Action.TOPIC_UNPIN
            ),
            target=topic,
        )
        return Response({'is_pinned': topic.is_pinned})


class TopicToggleLockView(APIView):
    """POST /forum/topics/{id}/toggle-lock — verrouille/déverrouille (staff only)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int, *args, **kwargs):
        if not request.user.is_staff:
            return Response(
                {'detail': 'Réservé au staff.', 'code': 'forbidden'},
                status=status.HTTP_403_FORBIDDEN,
            )
        topic = get_object_or_404(Topic, pk=pk)
        topic.is_locked = not topic.is_locked
        topic.save(update_fields=['is_locked'])
        from apps.admin_panel.audit import log_admin_action
        from apps.admin_panel.models import AdminAuditLog

        log_admin_action(
            request,
            (
                AdminAuditLog.Action.TOPIC_LOCK
                if topic.is_locked
                else AdminAuditLog.Action.TOPIC_UNLOCK
            ),
            target=topic,
        )
        return Response({'is_locked': topic.is_locked})


class ReplyToggleSolutionView(APIView):
    """POST /forum/replies/{id}/toggle-solution

    Marque une réponse comme "solution acceptée". Permission :
    - L'auteur du TOPIC (qui a posé la question)
    - OU le staff (modération)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int, *args, **kwargs):
        reply = get_object_or_404(
            Reply.objects.select_related('topic'),
            pk=pk,
        )
        is_topic_author = reply.topic.author_id == request.user.id
        if not (request.user.is_staff or is_topic_author):
            return Response(
                {
                    'detail': "Seul l'auteur du sujet ou le staff peut marquer une solution.",
                    'code': 'forbidden',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Une seule solution acceptée par topic : on unset les autres avant
        if not reply.is_solution:
            Reply.objects.filter(topic_id=reply.topic_id, is_solution=True).update(
                is_solution=False,
            )
        reply.is_solution = not reply.is_solution
        reply.save(update_fields=['is_solution'])
        # Audit log staff actions only (les owners c'est normal)
        if request.user.is_staff and reply.is_solution:
            from apps.admin_panel.audit import log_admin_action
            from apps.admin_panel.models import AdminAuditLog

            log_admin_action(
                request,
                AdminAuditLog.Action.REPLY_MARK_SOLUTION,
                target=reply,
            )
        return Response({'is_solution': reply.is_solution})


# ─── Upload images dans les posts du forum ───────────────────────────────
# Upload direct multipart (vs presigned pour les modèles 3D) car les images
# sont petites (~5MB max). Plus simple côté frontend = un seul POST.

# Types MIME autorisés pour les images du forum
_FORUM_IMAGE_ALLOWED_TYPES = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
}
_FORUM_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


class ForumImageUploadView(APIView):
    """POST /api/v1/forum/upload-image

    Upload une image pour insertion dans un post (topic ou reply).
    Auth requise. Stockage MinIO via django-storages.

    Input  : multipart/form-data avec champ `file` (image)
    Output : { url, filename, size_bytes, content_type }

    Validation :
    - Types acceptés : png, jpg, jpeg, gif, webp
    - Taille max : 5 MB
    - Renomme avec UUID pour éviter les collisions et masquer le nom original
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        upload = request.FILES.get('file')
        if not upload:
            return Response(
                {'detail': "Champ 'file' manquant.", 'code': 'no_file'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validation type
        content_type = (upload.content_type or '').lower()
        if content_type not in _FORUM_IMAGE_ALLOWED_TYPES:
            return Response(
                {
                    'detail': (
                        'Type de fichier non autorisé. '
                        f'Acceptés : {", ".join(sorted(_FORUM_IMAGE_ALLOWED_TYPES))}.'
                    ),
                    'code': 'invalid_type',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validation taille
        if upload.size > _FORUM_IMAGE_MAX_BYTES:
            return Response(
                {
                    'detail': (
                        f'Fichier trop volumineux ({upload.size} octets). '
                        f'Max : {_FORUM_IMAGE_MAX_BYTES // (1024 * 1024)} MB.'
                    ),
                    'code': 'too_large',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Génère une clé unique : forum/uploads/{user_id}/{YYYY}/{MM}/{uuid}.{ext}
        ext = _FORUM_IMAGE_ALLOWED_TYPES[content_type]
        now = timezone.now()
        key = (
            f'forum/uploads/{request.user.pk}/'
            f'{now.year:04d}/{now.month:02d}/'
            f'{uuid.uuid4().hex}{ext}'
        )

        # Upload via django-storages (utilise le backend S3/MinIO configuré)
        saved_key = default_storage.save(key, upload)
        url = default_storage.url(saved_key)

        # Trace l'upload pour le garbage collector des orphelins
        # (cleanup_forum_orphan_uploads). `used=False` jusqu'à ce qu'un
        # Topic/Reply soit sauvegardé avec cette image en `<img src>`.
        ForumUpload.objects.create(
            user=request.user,
            key=saved_key,
            url=url,
            content_type=content_type,
            size_bytes=upload.size,
        )

        return Response(
            {
                'url': url,
                'filename': Path(saved_key).name,
                'size_bytes': upload.size,
                'content_type': content_type,
            },
            status=status.HTTP_201_CREATED,
        )
