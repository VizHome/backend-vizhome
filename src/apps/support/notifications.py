"""Notifications email pour les tickets support.

Envoyé via Mailpit en dev (capture les mails sur localhost:8025), via
SMTP réel en prod. `fail_silently=True` car un email raté ne doit jamais
bloquer la création du ticket / message côté UX.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail

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
        User.objects
        .filter(is_staff=True, is_active=True)
        .values_list('email', flat=True),
    )


def notify_staff_new_ticket(ticket: SupportTicket) -> None:
    """Email envoyé aux staffs quand un nouveau ticket est ouvert.

    Tous les staffs actifs reçoivent l'email (file partagée façon helpdesk).
    """
    recipients = _staff_emails()
    if not recipients:
        return

    url = _frontend_ticket_url(ticket.pk, admin=True)
    first_msg = ticket.messages.order_by('created_at').first()
    body_preview = (first_msg.body[:300] + '…') if first_msg and len(first_msg.body) > 300 else (first_msg.body if first_msg else '')

    send_mail(
        subject=f'[Support #{ticket.pk}] {ticket.subject}',
        message=(
            f'Nouveau ticket de support ouvert par @{ticket.user.pseudo} '
            f'({ticket.user.email})\n\n'
            f'Catégorie : {ticket.get_category_display()}\n'
            f'Priorité  : {ticket.get_priority_display()}\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'{body_preview}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'Ouvrir le ticket dans l\'admin : {url}\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=True,
    )


def notify_user_staff_replied(message: SupportMessage) -> None:
    """Email envoyé à l'auteur du ticket quand le staff répond."""
    ticket = message.ticket
    user = ticket.user
    if not user.email:
        return

    url = _frontend_ticket_url(ticket.pk)
    body_preview = (message.body[:400] + '…') if len(message.body) > 400 else message.body

    send_mail(
        subject=f'[Support #{ticket.pk}] Nouvelle réponse de l\'équipe VizHome',
        message=(
            f'Bonjour @{user.pseudo},\n\n'
            f'Tu as reçu une nouvelle réponse sur ton ticket "{ticket.subject}" :\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'{body_preview}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'Voir la conversation : {url}\n\n'
            f'— L\'équipe VizHome'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )


def notify_staff_user_replied(message: SupportMessage) -> None:
    """Email envoyé à l'assignee staff (s'il y en a) quand le user répond.

    Note : on ne notifie QUE l'assignee — pas tous les staffs, pour éviter
    le spam. Si pas d'assignee (ticket open sans reply staff), pas d'email.
    """
    ticket = message.ticket
    if not ticket.assignee or not ticket.assignee.email:
        return

    url = _frontend_ticket_url(ticket.pk, admin=True)
    body_preview = (message.body[:300] + '…') if len(message.body) > 300 else message.body

    send_mail(
        subject=f'[Support #{ticket.pk}] @{ticket.user.pseudo} a répondu',
        message=(
            f'@{ticket.user.pseudo} a répondu sur "{ticket.subject}" :\n\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'{body_preview}\n'
            f'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            f'Ouvrir le ticket : {url}\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[ticket.assignee.email],
        fail_silently=True,
    )
