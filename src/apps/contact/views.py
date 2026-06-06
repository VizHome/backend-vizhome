"""Vue POST /api/v1/contact/ — envoie un email à l'équipe + opt-in newsletter."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, BaseThrottle
from rest_framework.views import APIView

from .models import NewsletterSubscriber
from .serializers import ContactMessageSerializer

logger = logging.getLogger(__name__)

# Adresse interne destinataire — surchargée par CONTACT_RECIPIENT_EMAIL en env
DEFAULT_RECIPIENT = 'contact@vizhome.fr'


class ContactRateThrottle(AnonRateThrottle):
    """Throttle dédié au form de contact (anti-spam)."""

    scope = 'contact'


class ContactView(APIView):
    """POST /api/v1/contact/ — public, rate-limited à 5/h par IP."""

    permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]
    throttle_classes: ClassVar[list[type[BaseThrottle]]] = [ContactRateThrottle]

    def post(self, request: Request) -> Response:
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload: dict[str, Any] = serializer.validated_data

        # 1. Email à l'équipe (contenu utile pour traiter la demande)
        self._send_team_email(payload)

        # 2. Opt-in newsletter (idempotent : update_or_create)
        if payload.get('newsletter_opt_in'):
            NewsletterSubscriber.objects.update_or_create(
                email=payload['email'].lower(),
                defaults={'source': 'contact_form', 'is_active': True},
            )

        return Response({'ok': True}, status=status.HTTP_200_OK)

    # ────────────────────────────────────────────────────────────────────
    def _send_team_email(self, payload: dict[str, Any]) -> None:
        recipient = getattr(settings, 'CONTACT_RECIPIENT_EMAIL', DEFAULT_RECIPIENT)
        subject_label = dict(ContactMessageSerializer.fields['subject'].choices).get(
            payload['subject'], payload['subject']
        )
        email_subject = f'[VizHome contact] {subject_label} — {payload["name"]}'

        # Plain text fallback
        text_body = render_to_string(
            'contact/team_email.txt',
            {'payload': payload, 'subject_label': subject_label},
        )
        html_body = render_to_string(
            'contact/team_email.html',
            {'payload': payload, 'subject_label': subject_label},
        )

        msg = EmailMultiAlternatives(
            subject=email_subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
            reply_to=[payload['email']],  # le staff répond direct au user
        )
        msg.attach_alternative(html_body, 'text/html')
        # `fail_silently=False` → erreur SMTP propagée → 500 + logs
        # (préférable à un faux succès qui laisse le user dans le noir).
        try:
            msg.send(fail_silently=False)
        except Exception:
            logger.exception('Failed to send contact email for %s', payload['email'])
            raise
