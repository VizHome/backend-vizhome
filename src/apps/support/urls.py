"""URLs support utilisateur (sous `/api/v1/support/`)."""

from django.urls import path

from .views import (
    TicketDetailView,
    TicketListCreateView,
    TicketMessageCreateView,
)

app_name = "support"

urlpatterns = [
    path("tickets", TicketListCreateView.as_view(), name="ticket-list"),
    path("tickets/<int:pk>", TicketDetailView.as_view(), name="ticket-detail"),
    path(
        "tickets/<int:pk>/messages",
        TicketMessageCreateView.as_view(),
        name="ticket-message",
    ),
]
