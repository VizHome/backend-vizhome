"""Serializers DRF pour billing."""
from __future__ import annotations

from rest_framework import serializers


class PlanSerializer(serializers.Serializer):
    """Représentation publique d'un plan (pour /api/v1/billing/plans)."""

    name = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    price_eur = serializers.IntegerField(allow_null=True)
    renders_limit = serializers.IntegerField()
    storage_limit_bytes = serializers.IntegerField()
    is_billable = serializers.BooleanField()


class CheckoutRequestSerializer(serializers.Serializer):
    """Body de POST /me/subscription/checkout."""

    plan = serializers.ChoiceField(choices=['pro', 'enterprise'])


class CheckoutResponseSerializer(serializers.Serializer):
    """Réponse de /me/subscription/checkout."""

    checkout_url = serializers.URLField()
    session_id = serializers.CharField()


class SubscriptionSerializer(serializers.Serializer):
    """État courant de la subscription du user."""

    has_subscription = serializers.BooleanField()
    plan = serializers.CharField()
    status = serializers.CharField(allow_null=True)
    current_period_end = serializers.DateTimeField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()


class InvoiceSerializer(serializers.Serializer):
    id = serializers.CharField()
    number = serializers.CharField(allow_null=True)
    amount_paid = serializers.IntegerField()  # cents
    currency = serializers.CharField()
    status = serializers.CharField()
    created = serializers.DateTimeField()
    hosted_invoice_url = serializers.URLField(allow_null=True)
    invoice_pdf = serializers.URLField(allow_null=True)


class PaymentMethodSerializer(serializers.Serializer):
    id = serializers.CharField()
    brand = serializers.CharField()
    last4 = serializers.CharField()
    exp_month = serializers.IntegerField()
    exp_year = serializers.IntegerField()
