"""Vues DRF RGPD : export + suppression de compte.

Tous les endpoints sont montés sous `/api/v1/me/` (cf `config/urls.py`).
L'utilisateur authentifié ne peut agir QUE sur ses propres données — pas
d'IDOR possible : on ignore tout `pk` URL et on filtre systématiquement
par `request.user`.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import JWTAuthenticationAllowInactive
from .models import DELETION_GRACE_PERIOD_DAYS, DeletionRequest, ExportRequest
from .serializers import (
    DeleteAccountInputSerializer,
    DeletionRequestSerializer,
    ExportRequestSerializer,
)


# ─── Export ──────────────────────────────────────────────────────────────────
class ExportDataView(APIView):
    """POST /me/export-data — déclenche la préparation d'un export RGPD.

    Idempotent côté UX : si une demande est déjà QUEUED ou PROCESSING,
    on la renvoie au lieu d'en créer une nouvelle (évite de dupliquer
    les jobs Celery si l'utilisateur clique deux fois).
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        # Réutilise une demande en cours si applicable
        existing = (
            ExportRequest.objects.filter(
                user=request.user,
                status__in=(
                    ExportRequest.Status.QUEUED,
                    ExportRequest.Status.PROCESSING,
                ),
            )
            .order_by('-requested_at')
            .first()
        )
        if existing is not None:
            return Response(
                ExportRequestSerializer(existing).data,
                status=status.HTTP_202_ACCEPTED,
            )

        export_req = ExportRequest.objects.create(user=request.user)

        # Déclenche la tâche Celery asynchrone (import local pour éviter
        # un cycle d'import au démarrage Django).
        from .tasks import build_user_export_zip

        build_user_export_zip.delay(export_req.pk)

        return Response(
            ExportRequestSerializer(export_req).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ExportDataStatusView(APIView):
    """GET /me/export-data/status — état de la dernière demande d'export."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        latest = ExportRequest.objects.filter(user=request.user).order_by('-requested_at').first()
        if latest is None:
            return Response(
                {
                    'detail': "Aucune demande d'export pour ce compte.",
                    'code': 'no_export',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Marque l'export expiré si l'échéance est passée (sans toucher au
        # storage : c'est le job du garbage collector).
        if (
            latest.status == ExportRequest.Status.READY
            and latest.expires_at is not None
            and latest.expires_at <= timezone.now()
        ):
            latest.status = ExportRequest.Status.EXPIRED
            latest.save(update_fields=['status'])

        return Response(ExportRequestSerializer(latest).data)


# ─── Suppression de compte ───────────────────────────────────────────────────
class RequestDeleteAccountView(APIView):
    """POST /me/delete-account — programme la suppression du compte (J+30).

    Effet immédiat :
    * `user.is_active = False` (l'utilisateur ne peut plus se connecter)
    * Toutes les sessions JWT existantes sont révoquées
    * Un `DeletionRequest` est créé avec `scheduled_for = now + 30j`

    Le hard delete est différé à la tâche Celery beat quotidienne
    `cleanup_pending_deletions`, qui appelle `user.delete()` (cascade
    sur projects/renders/forum/etc. via les ForeignKey existantes).
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        serializer = DeleteAccountInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        # Refuse si une demande active existe déjà
        existing = DeletionRequest.objects.filter(user=user).first()
        if existing and existing.is_pending:
            return Response(
                {
                    'detail': 'Une demande de suppression est déjà en cours.',
                    'code': 'already_scheduled',
                    'request': DeletionRequestSerializer(existing).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Si une ancienne demande annulée existe, on la remplace
        if existing is not None:
            existing.delete()

        deletion = DeletionRequest.objects.create(
            user=user,
            notes=serializer.validated_data.get('notes', ''),
        )

        # Soft delete immédiat
        user.is_active = False
        user.save(update_fields=['is_active'])

        # Révoque toutes les sessions JWT en cours
        from apps.accounts.models import UserSession

        UserSession.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )

        return Response(
            {
                'detail': (
                    f'Compte désactivé. La suppression définitive sera effective '
                    f'dans {DELETION_GRACE_PERIOD_DAYS} jours. Tu peux annuler '
                    f"tant que la suppression n'est pas effectuée."
                ),
                'request': DeletionRequestSerializer(deletion).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CancelDeleteAccountView(APIView):
    """POST /me/delete-account/cancel — annule la suppression programmée.

    Tant que la tâche cron n'a pas hard-delete l'utilisateur, on peut
    annuler. Le compte est réactivé (`is_active = True`).

    ⚠️ Auth particulière : on accepte les tokens JWT même si le compte est
    `is_active=False` (sinon impossible d'annuler après soft delete). On
    refuse en revanche si le hard delete a déjà eu lieu (user n'existe
    plus, le token devient invalide naturellement).
    """

    authentication_classes = (JWTAuthenticationAllowInactive,)
    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        try:
            deletion = DeletionRequest.objects.get(user=request.user)
        except DeletionRequest.DoesNotExist:
            return Response(
                {
                    'detail': 'Aucune demande de suppression à annuler.',
                    'code': 'no_deletion_request',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if deletion.completed_at is not None:
            return Response(
                {
                    'detail': 'La suppression a déjà été effectuée.',
                    'code': 'already_completed',
                },
                status=status.HTTP_410_GONE,
            )

        if deletion.cancelled_at is not None:
            # Déjà annulé — idempotent
            return Response(
                DeletionRequestSerializer(deletion).data,
                status=status.HTTP_200_OK,
            )

        deletion.cancelled_at = timezone.now()
        deletion.save(update_fields=['cancelled_at'])

        # Réactive le compte
        user = request.user
        user.is_active = True
        user.save(update_fields=['is_active'])

        return Response(DeletionRequestSerializer(deletion).data)
