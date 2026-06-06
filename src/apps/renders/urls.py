"""URL routing pour l'app renders."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("", views.RenderListCreateView.as_view(), name="renders-list"),
    path("history", views.RenderHistoryView.as_view(), name="renders-history"),
    path("<int:pk>", views.RenderDetailView.as_view(), name="renders-detail"),
]
