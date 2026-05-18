"""URL routing pour billing."""
from __future__ import annotations

from django.urls import path

from . import views

# Liste publique des plans (pas d'auth)
public_patterns = [
    path('plans', views.PlansListView.as_view(), name='plans'),
]

# Endpoints liés à l'utilisateur connecté
me_patterns = [
    path('subscription', views.SubscriptionView.as_view(), name='subscription'),
    path('subscription/checkout', views.CheckoutView.as_view(), name='subscription-checkout'),
    path('subscription/cancel', views.CancelSubscriptionView.as_view(), name='subscription-cancel'),
    path('invoices', views.InvoiceListView.as_view(), name='invoices'),
    path('payment-methods', views.PaymentMethodListView.as_view(), name='payment-methods'),
]
