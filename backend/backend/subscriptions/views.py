from datetime import datetime, timezone as dt_timezone

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status

from .models import SubscriptionPlan, Subscription
from .serializers import (
    CreateCheckoutSessionSerializer,
    CurrentSubscriptionSerializer,
    SubscriptionPlanSerializer,
)
from .services import StripeService


class SubscriptionPlanListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True).order_by("price_cents")
        data = SubscriptionPlanSerializer(plans, many=True).data
        return Response(data)


class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateCheckoutSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = get_object_or_404(SubscriptionPlan, pk=serializer.validated_data["plan_id"], is_active=True)
        result = StripeService.create_checkout_session(
            user_id=request.user.id,
            user_email=getattr(request.user, "email", None),
            plan=plan,
            success_url=serializer.validated_data["success_url"],
            cancel_url=serializer.validated_data["cancel_url"],
        )
        return Response({"id": result.id, "url": result.url}, status=status.HTTP_201_CREATED)


class CurrentSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = (
            Subscription.objects.filter(user=request.user)
            .select_related("plan")
            .order_by("-created_at")
            .first()
        )

        if subscription is None:
            return Response(
                {
                    "has_subscription": False,
                    "has_active_subscription": False,
                    "subscription": None,
                }
            )

        is_active = (
            subscription.status == Subscription.STATUS_ACTIVE
            and (
                subscription.current_period_end is None
                or subscription.current_period_end > timezone.now()
            )
        )
        data = CurrentSubscriptionSerializer(subscription).data
        return Response(
            {
                "has_subscription": True,
                "has_active_subscription": is_active,
                "subscription": data,
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = StripeService.construct_event(payload, sig_header)
        except Exception as exc:
            return HttpResponse(status=400, content=str(exc))

        # Handle events
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            subscription_id = session.get("subscription")
            metadata = session.get("metadata", {}) or {}
            user_id = metadata.get("user_id")
            plan_id = metadata.get("plan_id")

            if subscription_id and user_id and plan_id:
                # Retrieve subscription details from Stripe
                sub_obj = StripeService.retrieve_subscription(subscription_id)
                current_period_end_unix = sub_obj.get("current_period_end")
                status_str = sub_obj.get("status", Subscription.STATUS_INCOMPLETE)

                try:
                    plan = SubscriptionPlan.objects.get(pk=int(plan_id))
                except SubscriptionPlan.DoesNotExist:
                    return HttpResponse(status=200)  # Plan removed; ignore gracefully

                # Upsert the subscription
                subscription, _created = Subscription.objects.update_or_create(
                    stripe_subscription_id=subscription_id,
                    defaults={
                        "user_id": int(user_id),
                        "plan": plan,
                        "status": status_str,
                        "current_period_end": datetime.fromtimestamp(
                            current_period_end_unix, tz=dt_timezone.utc
                        )
                        if current_period_end_unix
                        else None,
                    },
                )

        elif event["type"] in {"customer.subscription.updated", "customer.subscription.deleted"}:
            sub = event["data"]["object"]
            subscription_id = sub.get("id")
            status_str = sub.get("status", Subscription.STATUS_INCOMPLETE)
            current_period_end_unix = sub.get("current_period_end")

            try:
                Subscription.objects.filter(stripe_subscription_id=subscription_id).update(
                    status=status_str,
                    current_period_end=datetime.fromtimestamp(
                        current_period_end_unix, tz=dt_timezone.utc
                    )
                    if current_period_end_unix
                    else None,
                )
            except Exception:
                pass  # swallow; nothing to update

        return HttpResponse(status=200)
