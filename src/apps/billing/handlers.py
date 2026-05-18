"""Webhook handlers Stripe — synchronise notre User.plan depuis les Subscriptions.

dj-stripe persiste tous les objets Stripe en DB et émet des signaux que
l'on écoute ici pour déclencher la logique métier propre à VizHome.
"""
from __future__ import annotations

import logging
from typing import Any

from djstripe import models as dj_models
from djstripe.event_handlers import djstripe_receiver

from apps.accounts.models import User, UserStats

from .plans import PLAN_CONFIG, get_plan_by_lookup_key

logger = logging.getLogger(__name__)


def _apply_plan_to_user(user: User, plan_name: str) -> None:
    """Met à jour le plan + ajuste les quotas associés."""
    config = PLAN_CONFIG[plan_name]
    user.plan = plan_name
    user.save(update_fields=['plan'])

    UserStats.objects.filter(user=user).update(
        renders_limit=config['renders_limit'],
        storage_limit_bytes=config['storage_limit_bytes'],
    )
    logger.info('User %s → plan %s', user.email, plan_name)


def _user_from_subscription(subscription: dj_models.Subscription) -> User | None:
    """Récupère notre User depuis une Subscription dj-stripe via Customer.subscriber."""
    customer = subscription.customer
    if not customer or not customer.subscriber_id:
        return None
    return User.objects.filter(pk=customer.subscriber_id).first()


@djstripe_receiver('customer.subscription.created')
@djstripe_receiver('customer.subscription.updated')
def on_subscription_change(event: dj_models.Event, **kwargs: Any) -> None:
    """Active/downgrade le plan suivant l'état de la subscription."""
    sub_id = event.data['object']['id']
    try:
        sub = dj_models.Subscription.objects.get(id=sub_id)
    except dj_models.Subscription.DoesNotExist:
        logger.warning('Subscription %s introuvable post-webhook', sub_id)
        return

    user = _user_from_subscription(sub)
    if not user:
        logger.warning('Pas de User lié à la Subscription %s', sub_id)
        return

    if sub.status not in ('active', 'trialing'):
        # Subscription en pause / impayée → on garde le plan actuel jusqu'à
        # expiration (l'event customer.subscription.deleted s'en chargera)
        return

    # Détermine le plan depuis le lookup_key de la première Price
    item = sub.items.first()
    if not item or not item.price.lookup_key:
        logger.warning('Subscription %s sans lookup_key Price, skip', sub_id)
        return

    plan_name = get_plan_by_lookup_key(item.price.lookup_key)
    if plan_name:
        _apply_plan_to_user(user, plan_name)


@djstripe_receiver('customer.subscription.deleted')
def on_subscription_deleted(event: dj_models.Event, **kwargs: Any) -> None:
    """Downgrade vers free quand une subscription est définitivement annulée."""
    sub_id = event.data['object']['id']
    sub = dj_models.Subscription.objects.filter(id=sub_id).first()
    if not sub:
        return

    user = _user_from_subscription(sub)
    if user and user.plan != User.Plan.FREE:
        _apply_plan_to_user(user, User.Plan.FREE)
