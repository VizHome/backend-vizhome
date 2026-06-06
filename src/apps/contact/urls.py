"""URLs de l'app `contact`."""

from __future__ import annotations

from django.urls import path

from .views import ContactView

urlpatterns = [
    path('', ContactView.as_view(), name='contact'),
]
