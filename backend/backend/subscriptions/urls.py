from django.urls import path

from .views import (
    CreateCheckoutSessionView,
    CurrentSubscriptionView,
    StripeWebhookView,
    SubscriptionPlanListView,
)

urlpatterns = [
    path("plans/", SubscriptionPlanListView.as_view(), name="plans-list"),
    path("checkout-session/", CreateCheckoutSessionView.as_view(), name="checkout-session"),
    path("me/", CurrentSubscriptionView.as_view(), name="current-subscription"),
    path("webhook/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
