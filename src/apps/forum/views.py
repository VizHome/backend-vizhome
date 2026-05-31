"""Vues DRF du forum."""
from __future__ import annotations

from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Category, Reply, Topic
from .permissions import IsAuthorOrStaff
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

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
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
        allowed = {'created_at', '-created_at', 'last_reply_at', '-last_reply_at',
                   'replies_count', '-replies_count', 'views_count', '-views_count'}
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
                {'detail': f"Seul le staff peut poster dans « {category.name} ».",
                 'code': 'category_locked'},
                status=status.HTTP_403_FORBIDDEN,
            )

        topic = serializer.save(author=request.user)
        # Re-slug avec l'id pour URLs uniques (`12-comment-importer-glb`)
        topic.slug = f'{topic.pk}-{topic.slug[:200]}'
        topic.save(update_fields=['slug'])

        output = TopicDetailSerializer(topic, context={'request': request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class TopicDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /forum/topics/{id}."""

    permission_classes = [IsAuthorOrStaff]
    serializer_class = TopicDetailSerializer

    def get_authenticators(self):
        if self.request.method == 'GET':
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), IsAuthorOrStaff()]

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

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_authenticators(self):
        if self.request.method == 'GET':
            return []
        return super().get_authenticators()

    def get_serializer_class(self):
        return ReplyCreateSerializer if self.request.method == 'POST' else ReplySerializer

    def get_queryset(self):
        return (
            Reply.objects
            .filter(topic_id=self.kwargs['topic_id'])
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
    """PATCH/DELETE /forum/replies/{id} — édition/suppression par auteur ou staff.

    GET inutile dans ce design (les replies se chargent via topic).
    """

    permission_classes = [IsAuthenticated, IsAuthorOrStaff]
    serializer_class = ReplySerializer

    def get_queryset(self):
        return Reply.objects.select_related('author', 'topic').all()
