"""Vues DRF pour le support."""

from __future__ import annotations

from django.db.models import BooleanField, Case, Count, Max, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import SupportCreateThrottle

from .models import SupportMessage, SupportTicket
from .serializers import (
    SupportMessageCreateSerializer,
    SupportMessageSerializer,
    SupportTicketCreateSerializer,
    SupportTicketDetailSerializer,
    SupportTicketListSerializer,
    SupportTicketUpdateStatusSerializer,
)


def _annotated_qs(qs):
    """Ajoute messages_count + last_message_at + last_message_from_staff.

    Ces colonnes alimentent les serializers list/detail sans N+1.
    """
    return qs.annotate(
        messages_count=Count('messages'),
        last_message_at=Max('messages__created_at'),
    )


def _attach_last_from_staff(tickets_iterable):
    """Post-processing pour `last_message_from_staff` (subquery serait lourde
    en SQL ; on fait un dict lookup en Python sur le batch déjà chargé)."""
    ticket_ids = [t.pk for t in tickets_iterable]
    if not ticket_ids:
        return
    last_per_ticket: dict[int, bool] = {}
    for msg in (
        SupportMessage.objects.filter(ticket_id__in=ticket_ids)
        .order_by('ticket_id', '-created_at')
        .values('ticket_id', 'from_staff')
    ):
        last_per_ticket.setdefault(msg['ticket_id'], msg['from_staff'])
    for t in tickets_iterable:
        t.last_message_from_staff = last_per_ticket.get(t.pk, False)


# ─── Endpoints utilisateur ────────────────────────────────────────────────
class TicketListCreateView(generics.ListCreateAPIView):
    """GET /api/v1/support/tickets — liste mes tickets (paginée).
    POST /api/v1/support/tickets — crée un nouveau ticket.
    """

    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        """Limite la création à 10 tickets/h/user (anti-spam, le GET reste libre)."""
        if self.request.method == 'POST':
            return [SupportCreateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        return _annotated_qs(
            SupportTicket.objects.filter(user=self.request.user)
            .select_related('user', 'assignee')
            .order_by('-updated_at')
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SupportTicketCreateSerializer
        return SupportTicketListSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            _attach_last_from_staff(page)
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        items = list(qs)
        _attach_last_from_staff(items)
        return Response(self.get_serializer(items, many=True).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = serializer.save()
        out = SupportTicketDetailSerializer(
            _annotated_qs(SupportTicket.objects.filter(pk=ticket.pk)).first(),
        )
        return Response(out.data, status=status.HTTP_201_CREATED)


class TicketDetailView(generics.RetrieveUpdateAPIView):
    """GET /api/v1/support/tickets/{id} — détail + messages.
    PATCH /api/v1/support/tickets/{id} — staff seulement (status/priority/assignee).

    Le user peut GET son propre ticket ; le staff voit tout.
    """

    serializer_class = SupportTicketDetailSerializer

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [IsAuthenticated(), IsAdminUser()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return SupportTicketUpdateStatusSerializer
        return SupportTicketDetailSerializer

    def get_queryset(self):
        qs = _annotated_qs(
            SupportTicket.objects.select_related('user', 'assignee').prefetch_related(
                'messages', 'messages__author'
            )
        )
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def perform_update(self, serializer):
        """Hook DRF : après save, set closed_at quand le ticket passe à closed."""
        instance = serializer.save()
        if instance.status == SupportTicket.Status.CLOSED and not instance.closed_at:
            instance.closed_at = timezone.now()
            instance.save(update_fields=['closed_at'])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        _attach_last_from_staff([instance])
        return Response(self.get_serializer(instance).data)


class TicketMessageCreateView(APIView):
    """POST /api/v1/support/tickets/{id}/messages — répond au ticket.

    L'auteur (user ou staff) ajoute un message à la conversation.
    Le status du ticket évolue automatiquement :
    - Reply staff → status passe à PENDING + assigne si pas encore fait
    - Reply user sur un ticket RESOLVED → repasse en PENDING (le user
      n'est finalement pas satisfait).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int, *args, **kwargs):
        if request.user.is_staff:
            ticket = get_object_or_404(SupportTicket, pk=pk)
        else:
            ticket = get_object_or_404(SupportTicket, pk=pk, user=request.user)

        if ticket.status == SupportTicket.Status.CLOSED:
            return Response(
                {'detail': 'Ce ticket est fermé.', 'code': 'ticket_closed'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SupportMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        msg = SupportMessage.objects.create(
            ticket=ticket,
            author=request.user,
            from_staff=request.user.is_staff,
            body=serializer.validated_data['body'],
        )

        # Transition automatique du statut
        updated_fields: list[str] = []
        if request.user.is_staff:
            if ticket.assignee is None:
                ticket.assignee = request.user
                updated_fields.append('assignee')
            if ticket.status == SupportTicket.Status.OPEN:
                ticket.status = SupportTicket.Status.PENDING
                updated_fields.append('status')
        else:
            # User répond après que staff ait marqué résolu → réouverture
            if ticket.status == SupportTicket.Status.RESOLVED:
                ticket.status = SupportTicket.Status.PENDING
                updated_fields.append('status')
        if updated_fields:
            ticket.save(update_fields=[*updated_fields, 'updated_at'])

        # Notifie l'autre partie (fail_silently à l'intérieur).
        from .notifications import (
            notify_staff_user_replied,
            notify_user_staff_replied,
        )

        if request.user.is_staff:
            notify_user_staff_replied(msg)
        else:
            notify_staff_user_replied(msg)

        return Response(
            SupportMessageSerializer(msg).data,
            status=status.HTTP_201_CREATED,
        )


# ─── Endpoint admin (liste tous les tickets, paginé + filtres) ────────────
class AdminTicketListView(generics.ListAPIView):
    """GET /api/v1/admin/support/tickets — liste paginée pour staff.

    Filtres : `status`, `priority`, `category`, `assignee`, `search` (sujet),
    `unassigned=true` (sans assignee).
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = SupportTicketListSerializer

    def get_queryset(self):
        qs = _annotated_qs(SupportTicket.objects.select_related('user', 'assignee'))
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('priority'):
            qs = qs.filter(priority=params['priority'])
        if params.get('category'):
            qs = qs.filter(category=params['category'])
        if params.get('assignee'):
            qs = qs.filter(assignee_id=params['assignee'])
        if params.get('unassigned') == 'true':
            qs = qs.filter(assignee__isnull=True)
        if params.get('search'):
            qs = qs.filter(
                Q(subject__icontains=params['search'])
                | Q(user__email__icontains=params['search'])
                | Q(user__pseudo__icontains=params['search']),
            )
        ordering = params.get('ordering', '-updated_at')
        return qs.order_by(ordering)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            _attach_last_from_staff(page)
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        items = list(qs)
        _attach_last_from_staff(items)
        return Response(self.get_serializer(items, many=True).data)


# Helper : aussi exposer ce queryset annoté plus haut sur d'autres apps (unused warning)
_unused = Case
_unused2 = When
_unused3 = Value
_unused4 = BooleanField
