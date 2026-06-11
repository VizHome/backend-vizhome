"""Notifications email pour les tickets support.

Envoyé via Mailpit en dev (capture les mails sur localhost:8025), via
SMTP réel en prod. `fail_silently=True` car un email raté ne doit jamais
bloquer la création du ticket / message côté UX.

Les emails sont rendus HTML + texte via les templates brandés
`emails/support_*.html|txt` (cf apps.core.emails.send_templated_email).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.core.emails import send_templated_email

from .models import SupportMessage, SupportTicket

User = get_user_model()


def _frontend_ticket_url(ticket_id: int, *, admin: bool = False) -> str:
    """Lien profond vers la page du ticket dans le frontend Nuxt."""
    base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    if admin:
        return f'{base}/admin/support'  # liste admin, le staff cliquera sur le ticket
    return f'{base}/support/{ticket_id}'


def _staff_emails() -> list[str]:
    """Liste des emails staff actifs à notifier des nouveaux tickets."""
    return list(
        User.objects.filter(is_staff=True, is_active=True).values_list('email', flat=True),
    )


def _preview(text: str, limit: int) -> str:
    return (text[:limit] + '…') if len(text) > limit else text


def notify_staff_new_ticket(ticket: SupportTicket) -> None:
    """Email envoyé aux staffs quand un nouveau ticket est ouvert.

    Tous les staffs actifs reçoivent l'email (file partagée façon helpdesk).
    """
    recipients = _staff_emails()
    if not recipients:
        return

    first_msg = ticket.messages.order_by('created_at').first()
    send_templated_email(
        subject=f'[Support #{ticket.pk}] {ticket.subject}',
        recipients=recipients,
        template='support_new_ticket',
        context={
            'ticket_id': ticket.pk,
            'ticket_subject': ticket.subject,
            'pseudo': ticket.user.pseudo,
            'user_email': ticket.user.email,
            'category': ticket.get_category_display(),
            'priority': ticket.get_priority_display(),
            'body_preview': _preview(first_msg.body if first_msg else '', 300),
            'cta_url': _frontend_ticket_url(ticket.pk, admin=True),
            'cta_label': 'Ouvrir le ticket',
            'preheader': f'Nouveau ticket de @{ticket.user.pseudo}',
        },
    )


def notify_user_staff_replied(message: SupportMessage) -> None:
    """Email envoyé à l'auteur du ticket quand le staff répond."""
    ticket = message.ticket
    user = ticket.user
    if not user.email:
        return

    send_templated_email(
        subject=f"[Support #{ticket.pk}] Nouvelle réponse de l'équipe VizHome",
        recipients=[user.email],
        template='support_staff_reply',
        context={
            'ticket_id': ticket.pk,
            'ticket_subject': ticket.subject,
            'pseudo': user.pseudo,
            'body_preview': _preview(message.body, 400),
            'cta_url': _frontend_ticket_url(ticket.pk),
            'cta_label': 'Voir la conversation',
            'preheader': "L'équipe VizHome a répondu à ton ticket",
        },
    )


def notify_staff_user_replied(message: SupportMessage) -> None:
    """Email envoyé à l'assignee staff (s'il y en a) quand le user répond.

    Note : on ne notifie QUE l'assignee — pas tous les staffs, pour éviter
    le spam. Si pas d'assignee (ticket open sans reply staff), pas d'email.
    """
    ticket = message.ticket
    if not ticket.assignee or not ticket.assignee.email:
        return

    send_templated_email(
        subject=f'[Support #{ticket.pk}] @{ticket.user.pseudo} a répondu',
        recipients=[ticket.assignee.email],
        template='support_user_reply',
        context={
            'ticket_id': ticket.pk,
            'ticket_subject': ticket.subject,
            'pseudo': ticket.user.pseudo,
            'body_preview': _preview(message.body, 300),
            'cta_url': _frontend_ticket_url(ticket.pk, admin=True),
            'cta_label': 'Ouvrir le ticket',
            'preheader': f'Réponse de @{ticket.user.pseudo} sur le ticket #{ticket.pk}',
        },
    )
