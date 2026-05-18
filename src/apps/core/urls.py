"""URLs pour les endpoints transverses (healthcheck)."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path('live', views.liveness, name='health-live'),
    path('ready', views.readiness, name='health-ready'),
]
