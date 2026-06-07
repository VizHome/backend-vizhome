"""URL routing pour l'app renders."""

from __future__ import annotations

from django.urls import path

from . import views
from .sse import RenderSSEView

urlpatterns = [
    path("", views.RenderListCreateView.as_view(), name="renders-list"),
    path("history", views.RenderHistoryView.as_view(), name="renders-history"),
    path("<int:pk>", views.RenderDetailView.as_view(), name="renders-detail"),
    path("<int:pk>/events", RenderSSEView.as_view(), name="renders-events"),
]
