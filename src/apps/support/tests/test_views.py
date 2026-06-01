"""Tests des endpoints support — création, replies, transitions de statut, perms."""
from __future__ import annotations

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.support.models import SupportMessage, SupportTicket


# ─── Création ──────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_create_ticket_requires_auth(api_client: APIClient):
    """POST /support/tickets sans auth → 401."""
    res = api_client.post('/api/v1/support/tickets', {
        'subject': 'Test', 'category': 'other', 'priority': 'medium', 'body': 'corps',
    }, format='json')
    assert res.status_code == 401


@pytest.mark.django_db
def test_create_ticket_happy_path(auth_client: APIClient, user: User):
    """POST avec un body valide crée le ticket + 1er message."""
    res = auth_client.post('/api/v1/support/tickets', {
        'subject': 'Mon rendu IA est cassé',
        'category': 'technical',
        'priority': 'high',
        'body': 'Le rendu #42 reste en pending depuis 1h, peut-on regarder ?',
    }, format='json')
    assert res.status_code == 201, res.data
    assert res.data['subject'] == 'Mon rendu IA est cassé'
    assert res.data['status'] == SupportTicket.Status.OPEN
    assert res.data['priority'] == SupportTicket.Priority.HIGH
    assert res.data['messages_count'] == 1
    assert len(res.data['messages']) == 1
    msg = res.data['messages'][0]
    assert msg['from_staff'] is False
    assert msg['body'].startswith('Le rendu #42')

    # Vérifie le state en DB
    ticket = SupportTicket.objects.get(pk=res.data['id'])
    assert ticket.user == user
    assert ticket.messages.count() == 1


@pytest.mark.django_db
def test_create_ticket_validates_subject_min_length(auth_client: APIClient):
    """Subject < 5 chars → 400."""
    res = auth_client.post('/api/v1/support/tickets', {
        'subject': 'oui', 'category': 'other', 'priority': 'medium', 'body': 'corps assez long',
    }, format='json')
    assert res.status_code == 400
    assert 'subject' in res.data


@pytest.mark.django_db
def test_create_ticket_validates_body_min_length(auth_client: APIClient):
    """Body < 2 chars → 400."""
    res = auth_client.post('/api/v1/support/tickets', {
        'subject': 'Sujet valide ici',
        'category': 'other', 'priority': 'medium',
        'body': '',
    }, format='json')
    assert res.status_code == 400


# ─── Listing ───────────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_list_tickets_returns_only_mine(
    auth_client: APIClient, other_client: APIClient,
):
    """GET /support/tickets ne renvoie que mes tickets, pas ceux des autres."""
    # Alice crée 2 tickets
    for i in range(2):
        auth_client.post('/api/v1/support/tickets', {
            'subject': f'Alice ticket {i}',
            'category': 'other', 'priority': 'medium',
            'body': 'Mon problème détaillé ici.',
        }, format='json')
    # Bob crée 1 ticket
    other_client.post('/api/v1/support/tickets', {
        'subject': 'Bob ticket',
        'category': 'other', 'priority': 'medium',
        'body': 'Mon problème détaillé ici.',
    }, format='json')

    # Alice ne voit que les siens
    res = auth_client.get('/api/v1/support/tickets')
    assert res.status_code == 200
    assert res.data['count'] == 2
    for t in res.data['results']:
        assert t['subject'].startswith('Alice')


@pytest.mark.django_db
def test_list_includes_messages_count_annotation(auth_client: APIClient, ticket: SupportTicket):
    """messages_count est annoté côté serveur (pas N+1)."""
    res = auth_client.get('/api/v1/support/tickets')
    assert res.status_code == 200
    t = res.data['results'][0]
    assert t['messages_count'] == 1
    assert t['last_message_from_staff'] is False


# ─── Détail + permissions ──────────────────────────────────────────────────
@pytest.mark.django_db
def test_get_own_ticket(auth_client: APIClient, ticket: SupportTicket):
    res = auth_client.get(f'/api/v1/support/tickets/{ticket.pk}')
    assert res.status_code == 200
    assert res.data['subject'] == ticket.subject
    assert len(res.data['messages']) == 1


@pytest.mark.django_db
def test_get_other_user_ticket_returns_404(other_client: APIClient, ticket: SupportTicket):
    """Bob ne peut pas voir le ticket d'Alice → 404 (pas 403, pour ne pas révéler son existence)."""
    res = other_client.get(f'/api/v1/support/tickets/{ticket.pk}')
    assert res.status_code == 404


@pytest.mark.django_db
def test_staff_can_see_any_ticket(staff_client: APIClient, ticket: SupportTicket):
    res = staff_client.get(f'/api/v1/support/tickets/{ticket.pk}')
    assert res.status_code == 200
    assert res.data['user_email'] == ticket.user.email


# ─── Replies + transitions de status ───────────────────────────────────────
@pytest.mark.django_db
def test_user_reply_appends_message(auth_client: APIClient, ticket: SupportTicket):
    """User répond à son propre ticket — message ajouté, from_staff=False."""
    res = auth_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'Voici un complément d\'information.',
    }, format='json')
    assert res.status_code == 201
    assert res.data['from_staff'] is False
    assert ticket.messages.count() == 2


@pytest.mark.django_db
def test_staff_reply_transitions_open_to_pending(
    staff_client: APIClient, staff_user: User, ticket: SupportTicket,
):
    """1ère reply staff sur open → status=pending + assignee=staff."""
    assert ticket.status == SupportTicket.Status.OPEN
    assert ticket.assignee is None

    res = staff_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'On regarde, peux-tu me donner ton user_id ?',
    }, format='json')
    assert res.status_code == 201
    assert res.data['from_staff'] is True

    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.PENDING
    assert ticket.assignee == staff_user


@pytest.mark.django_db
def test_user_reply_on_resolved_reopens_to_pending(
    auth_client: APIClient, ticket: SupportTicket,
):
    """User pas content après "résolu" → repasse en pending."""
    ticket.status = SupportTicket.Status.RESOLVED
    ticket.save()

    res = auth_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'Toujours pas réglé en fait.',
    }, format='json')
    assert res.status_code == 201

    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.PENDING


@pytest.mark.django_db
def test_reply_on_closed_ticket_returns_403(
    auth_client: APIClient, ticket: SupportTicket,
):
    """Aucune reply possible sur un ticket fermé."""
    ticket.mark_closed()

    res = auth_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'Encore quelque chose.',
    }, format='json')
    assert res.status_code == 403
    assert res.data.get('code') == 'ticket_closed'


@pytest.mark.django_db
def test_reply_body_validation(auth_client: APIClient, ticket: SupportTicket):
    """Body trop court → 400."""
    res = auth_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': ' ',
    }, format='json')
    assert res.status_code == 400


# ─── PATCH status (staff seulement) ────────────────────────────────────────
@pytest.mark.django_db
def test_staff_can_patch_status(staff_client: APIClient, ticket: SupportTicket):
    res = staff_client.patch(f'/api/v1/support/tickets/{ticket.pk}', {
        'status': 'resolved',
    }, format='json')
    assert res.status_code == 200
    ticket.refresh_from_db()
    assert ticket.status == SupportTicket.Status.RESOLVED


@pytest.mark.django_db
def test_user_cannot_patch_status(auth_client: APIClient, ticket: SupportTicket):
    res = auth_client.patch(f'/api/v1/support/tickets/{ticket.pk}', {
        'status': 'closed',
    }, format='json')
    assert res.status_code == 403


@pytest.mark.django_db
def test_closing_ticket_sets_closed_at(
    staff_client: APIClient, ticket: SupportTicket,
):
    """PATCH status=closed → closed_at est set automatiquement."""
    assert ticket.closed_at is None
    res = staff_client.patch(f'/api/v1/support/tickets/{ticket.pk}', {
        'status': 'closed',
    }, format='json')
    assert res.status_code == 200
    ticket.refresh_from_db()
    assert ticket.closed_at is not None


# ─── Admin endpoint ────────────────────────────────────────────────────────
@pytest.mark.django_db
def test_admin_endpoint_requires_staff(auth_client: APIClient):
    res = auth_client.get('/api/v1/admin/support/tickets')
    assert res.status_code == 403


@pytest.mark.django_db
def test_admin_endpoint_lists_all_tickets(
    staff_client: APIClient, ticket: SupportTicket, other_client: APIClient,
):
    """Admin voit le ticket d'Alice + ceux des autres."""
    # Bob crée un ticket
    other_client.post('/api/v1/support/tickets', {
        'subject': 'Bob support', 'category': 'billing',
        'priority': 'low', 'body': 'Question facturation.',
    }, format='json')

    res = staff_client.get('/api/v1/admin/support/tickets')
    assert res.status_code == 200
    assert res.data['count'] == 2


@pytest.mark.django_db
def test_admin_filter_by_status(
    staff_client: APIClient, ticket: SupportTicket,
):
    """Filter status=open ne renvoie que les ouverts."""
    # Ferme le ticket existant
    ticket.mark_closed()

    res_closed = staff_client.get('/api/v1/admin/support/tickets?status=closed')
    assert res_closed.data['count'] == 1

    res_open = staff_client.get('/api/v1/admin/support/tickets?status=open')
    assert res_open.data['count'] == 0


# ─── Notifications email ───────────────────────────────────────────────────
@pytest.mark.django_db
def test_create_ticket_notifies_staff(
    auth_client: APIClient, staff_user: User,
):
    """Création d'un ticket → mail aux staffs actifs."""
    mail.outbox.clear()
    res = auth_client.post('/api/v1/support/tickets', {
        'subject': 'Bug critique', 'category': 'technical',
        'priority': 'urgent', 'body': 'Le service est down.',
    }, format='json')
    assert res.status_code == 201
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert staff_user.email in sent.to
    assert 'Bug critique' in sent.subject
    assert '@alice' in sent.body  # pseudo du créateur


@pytest.mark.django_db
def test_staff_reply_notifies_user(
    staff_client: APIClient, user: User, ticket: SupportTicket,
):
    """Reply staff → email à l'auteur du ticket."""
    mail.outbox.clear()
    res = staff_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'On regarde ça maintenant.',
    }, format='json')
    assert res.status_code == 201
    assert len(mail.outbox) == 1
    assert user.email in mail.outbox[0].to
    assert 'Nouvelle réponse' in mail.outbox[0].subject


@pytest.mark.django_db
def test_user_reply_without_assignee_no_email(
    auth_client: APIClient, ticket: SupportTicket,
):
    """User répond mais pas d'assignee staff → aucun email envoyé."""
    assert ticket.assignee is None
    mail.outbox.clear()
    res = auth_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'Complément.',
    }, format='json')
    assert res.status_code == 201
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_user_reply_notifies_assignee_only(
    auth_client: APIClient, ticket: SupportTicket, staff_user: User,
):
    """User répond sur ticket assigné → seul l'assignee reçoit le mail (pas tous les staffs)."""
    ticket.assignee = staff_user
    ticket.save()
    mail.outbox.clear()

    res = auth_client.post(f'/api/v1/support/tickets/{ticket.pk}/messages', {
        'body': 'Complément d\'info.',
    }, format='json')
    assert res.status_code == 201
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [staff_user.email]


# ─── Pseudo affichage (régression) ─────────────────────────────────────────
@pytest.mark.django_db
def test_message_author_exposes_pseudo(auth_client: APIClient, user: User, ticket: SupportTicket):
    """L'auteur des messages doit exposer pseudo (utilisé partout côté UI)."""
    res = auth_client.get(f'/api/v1/support/tickets/{ticket.pk}')
    assert res.status_code == 200
    msg = res.data['messages'][0]
    assert msg['author']['pseudo'] == user.pseudo
    assert msg['author']['id'] == user.id


# ─── Signal/transitions consolidées ────────────────────────────────────────
@pytest.mark.django_db
def test_full_conversation_flow(
    auth_client: APIClient, staff_client: APIClient,
    user: User, staff_user: User,
):
    """Scenario complet : open → staff reply → user reply → staff resolve → user re-open."""
    # 1. User crée
    r1 = auth_client.post('/api/v1/support/tickets', {
        'subject': 'Bug critique avec l\'export',
        'category': 'technical', 'priority': 'urgent',
        'body': 'L\'export PNG bug systématiquement.',
    }, format='json')
    assert r1.status_code == 201
    tid = r1.data['id']

    t = SupportTicket.objects.get(pk=tid)
    assert t.status == SupportTicket.Status.OPEN
    assert t.assignee is None

    # 2. Staff répond → pending + assigne
    r2 = staff_client.post(f'/api/v1/support/tickets/{tid}/messages', {
        'body': 'Pris en charge, on regarde.',
    }, format='json')
    assert r2.status_code == 201
    t.refresh_from_db()
    assert t.status == SupportTicket.Status.PENDING
    assert t.assignee == staff_user

    # 3. User répond → reste pending
    auth_client.post(f'/api/v1/support/tickets/{tid}/messages', {
        'body': 'Voici un screenshot.',
    }, format='json')
    t.refresh_from_db()
    assert t.status == SupportTicket.Status.PENDING

    # 4. Staff résout
    staff_client.patch(f'/api/v1/support/tickets/{tid}', {
        'status': 'resolved',
    }, format='json')
    t.refresh_from_db()
    assert t.status == SupportTicket.Status.RESOLVED

    # 5. User pas content → re-open en pending
    auth_client.post(f'/api/v1/support/tickets/{tid}/messages', {
        'body': 'Toujours pas bon.',
    }, format='json')
    t.refresh_from_db()
    assert t.status == SupportTicket.Status.PENDING

    # 6. Staff ferme → closed_at set
    staff_client.patch(f'/api/v1/support/tickets/{tid}', {
        'status': 'closed',
    }, format='json')
    t.refresh_from_db()
    assert t.status == SupportTicket.Status.CLOSED
    assert t.closed_at is not None

    # 7. Reply impossible après closed
    r7 = auth_client.post(f'/api/v1/support/tickets/{tid}/messages', {
        'body': 'Hello?',
    }, format='json')
    assert r7.status_code == 403

    # Total messages : 4 (1 initial + 1 staff + 1 user + 1 user re-open)
    assert SupportMessage.objects.filter(ticket=t).count() == 4
