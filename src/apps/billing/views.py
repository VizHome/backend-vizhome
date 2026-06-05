"""Vues DRF pour billing."""

from __future__ import annotations

from django.conf import settings
from djstripe import models as dj_models
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .plans import PLAN_CONFIG, get_billable_plans
from .serializers import (
    CheckoutRequestSerializer,
    CheckoutResponseSerializer,
    InvoiceSerializer,
    PaymentMethodSerializer,
    PlanSerializer,
    SubscriptionSerializer,
)
from .stripe_client import StripeNotConfigured, get_stripe_client, is_configured


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _stripe_unavailable_response() -> Response:
    return Response(
        {
            "detail": "Stripe n'est pas configuré sur ce serveur.",
            "code": "stripe_unavailable",
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _get_or_create_customer(user) -> dj_models.Customer:
    """Trouve ou crée le Customer Stripe pour un user."""
    customer, _ = dj_models.Customer.get_or_create(subscriber=user)
    return customer


_ACTIVE_STATUSES = ("active", "trialing", "past_due")


def _sub_field(sub, name: str, default=None):
    """Accès défensif aux champs d'une djstripe.Subscription.

    Selon la version de djstripe, `status`, `current_period_end`,
    `cancel_at_period_end`, etc. peuvent être soit des colonnes directes,
    soit dans `stripe_data` (JSONField). On essaie les deux.
    """
    val = getattr(sub, name, None)
    if val is None:
        stripe_data = getattr(sub, "stripe_data", None) or {}
        val = stripe_data.get(name)
    return val if val is not None else default


def _get_active_subscription(
    customer: dj_models.Customer,
) -> dj_models.Subscription | None:
    """Récupère la subscription active du Customer (filtre en Python).

    On n'utilise pas `.filter(status__in=...)` côté SQL car selon la
    version de djstripe, `status` n'est pas une colonne — c'est une
    clé du JSONField `stripe_data`. Filtrer en Python évite la
    FieldError.
    """
    for sub in customer.subscriptions.all():
        status = _sub_field(sub, "status")
        if status in _ACTIVE_STATUSES:
            return sub
    return None


# ─── Plans (public catalog) ───────────────────────────────────────────────────
class PlansListView(APIView):
    """GET /api/v1/billing/plans — catalogue public des plans VizHome."""

    permission_classes = []
    authentication_classes = []

    def get(self, request: Request) -> Response:
        plans = [
            {
                "name": name,
                "label": cfg["label"],
                "description": cfg["description"],
                "price_eur": cfg["price_eur"],
                "renders_limit": cfg["renders_limit"],
                "storage_limit_bytes": cfg["storage_limit_bytes"],
                "is_billable": cfg["stripe_lookup_key"] is not None,
            }
            for name, cfg in PLAN_CONFIG.items()
        ]
        return Response(PlanSerializer(plans, many=True).data)


# ─── Subscription ─────────────────────────────────────────────────────────────
class SubscriptionView(APIView):
    """GET /api/v1/me/subscription — état courant de la subscription du user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user

        if not is_configured():
            return Response(
                SubscriptionSerializer(
                    {
                        "has_subscription": False,
                        "plan": user.plan,
                        "status": None,
                        "current_period_end": None,
                        "cancel_at_period_end": False,
                    }
                ).data
            )

        customer = dj_models.Customer.objects.filter(subscriber=user).first()
        sub = _get_active_subscription(customer) if customer else None

        return Response(
            SubscriptionSerializer(
                {
                    "has_subscription": sub is not None,
                    "plan": user.plan,
                    "status": _sub_field(sub, "status") if sub else None,
                    "current_period_end": (
                        _sub_field(sub, "current_period_end") if sub else None
                    ),
                    "cancel_at_period_end": (
                        _sub_field(sub, "cancel_at_period_end", False) if sub else False
                    ),
                }
            ).data
        )


class CheckoutView(APIView):
    """POST /api/v1/me/subscription/checkout — crée une Checkout Session Stripe."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not is_configured():
            return _stripe_unavailable_response()

        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan_name = serializer.validated_data["plan"]
        plan = PLAN_CONFIG[plan_name]
        lookup_key = plan["stripe_lookup_key"]

        try:
            stripe = get_stripe_client()
            # Récupère la Price par lookup_key (créée par setup_stripe_products)
            prices = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1)
            if not prices.data:
                return Response(
                    {
                        "detail": (
                            f"Aucune Price Stripe pour le plan '{plan_name}'. "
                            f"Lance `manage.py setup_stripe_products` d'abord."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            price_id = prices.data[0].id

            customer = _get_or_create_customer(request.user)

            session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=f"{settings.FRONTEND_URL}/account/billing?checkout=success",
                cancel_url=f"{settings.FRONTEND_URL}/account/billing?checkout=cancel",
                allow_promotion_codes=True,
                metadata={"plan": plan_name, "user_id": str(request.user.pk)},
            )
        except StripeNotConfigured:
            return _stripe_unavailable_response()

        return Response(
            CheckoutResponseSerializer(
                {
                    "checkout_url": session.url,
                    "session_id": session.id,
                }
            ).data
        )


class CancelSubscriptionView(APIView):
    """POST /api/v1/me/subscription/cancel — programme l'annulation en fin de période."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not is_configured():
            return _stripe_unavailable_response()

        customer = dj_models.Customer.objects.filter(subscriber=request.user).first()
        sub = _get_active_subscription(customer) if customer else None
        if not sub:
            return Response(
                {"detail": "Aucune subscription active à annuler."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stripe = get_stripe_client()
        stripe.Subscription.modify(sub.id, cancel_at_period_end=True)

        return Response(
            {
                "detail": "L'abonnement sera annulé à la fin de la période en cours.",
                "cancel_at_period_end": True,
            }
        )


# ─── Invoices ─────────────────────────────────────────────────────────────────
class InvoiceListView(APIView):
    """GET /api/v1/me/invoices — liste les factures Stripe du user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        customer = dj_models.Customer.objects.filter(subscriber=request.user).first()
        if not customer:
            return Response([])

        invoices = customer.invoices.all().order_by("-created")[:50]
        data = [
            {
                "id": inv.id,
                "number": inv.number,
                "amount_paid": inv.amount_paid,
                "currency": inv.currency,
                "status": inv.status,
                "created": inv.created,
                "hosted_invoice_url": inv.hosted_invoice_url,
                "invoice_pdf": inv.invoice_pdf,
            }
            for inv in invoices
        ]
        return Response(InvoiceSerializer(data, many=True).data)


# ─── Payment methods ──────────────────────────────────────────────────────────
class PaymentMethodListView(APIView):
    """GET /api/v1/me/payment-methods — liste les cartes du user."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        customer = dj_models.Customer.objects.filter(subscriber=request.user).first()
        if not customer:
            return Response([])

        methods = dj_models.PaymentMethod.objects.filter(customer=customer)
        data = []
        for pm in methods:
            card = pm.card or {}
            data.append(
                {
                    "id": pm.id,
                    "brand": card.get("brand", "?"),
                    "last4": card.get("last4", "????"),
                    "exp_month": card.get("exp_month", 0),
                    "exp_year": card.get("exp_year", 0),
                }
            )
        return Response(PaymentMethodSerializer(data, many=True).data)
