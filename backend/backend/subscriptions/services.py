from dataclasses import dataclass
from typing import Optional, Dict, Any

import stripe
from django.conf import settings

from .models import SubscriptionPlan


@dataclass
class CheckoutSessionResult:
    id: str
    url: str


class StripeService:
    @staticmethod
    def init_api() -> None:
        stripe.api_key = settings.STRIPE_SECRET_KEY

    @staticmethod
    def create_checkout_session(
        *,
        user_id: int,
        user_email: Optional[str],
        plan: SubscriptionPlan,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSessionResult:
        StripeService.init_api()
        metadata: Dict[str, Any] = {
            "user_id": str(user_id),
            "plan_id": str(plan.id),
        }
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            customer_email=user_email or None,
            metadata=metadata,
            allow_promotion_codes=True,
            billing_address_collection="auto",
            payment_method_types=["card"],
            automatic_tax={"enabled": False},
        )
        return CheckoutSessionResult(id=session["id"], url=session["url"])

    @staticmethod
    def retrieve_subscription(subscription_id: str) -> Dict[str, Any]:
        StripeService.init_api()
        return stripe.Subscription.retrieve(subscription_id)

    @staticmethod
    def construct_event(payload: bytes, sig_header: str) -> stripe.Event:
        StripeService.init_api()
        return stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
