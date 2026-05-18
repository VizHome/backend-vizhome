"""Vues DRF de l'app renders."""
from __future__ import annotations

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Render
from .serializers import (
    RenderCreateSerializer,
    RenderSerializer,
    RenderUpdateSerializer,
)
from .tasks import generate_render


class RenderListCreateView(generics.ListCreateAPIView):
    """GET /renders : galerie paginée. POST /renders : crée + déclenche Celery."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Render.objects.filter(user=self.request.user)

        # Filtre optionnel ?source=prompt|sketch|screenshot
        source = self.request.query_params.get('source')
        if source:
            qs = qs.filter(source=source)

        # Filtre optionnel ?status=done|failed|...
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return qs

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RenderCreateSerializer
        return RenderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        render = serializer.save()

        # Déclenche Celery (non bloquant)
        generate_render.delay(render.pk)

        output = RenderSerializer(render, context={'request': request})
        return Response(output.data, status=status.HTTP_202_ACCEPTED)


class RenderDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /renders/{id}."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Render.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return RenderUpdateSerializer
        return RenderSerializer


class RenderHistoryView(generics.ListAPIView):
    """GET /renders/history : 10 derniers prompts du user (pour l'autocomplete frontend).

    N'inclut que les renders de source=prompt et status=done.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RenderSerializer
    pagination_class = None

    def get_queryset(self):
        return Render.objects.filter(
            user=self.request.user,
            source=Render.Source.PROMPT,
            status=Render.Status.DONE,
        )[:10]
