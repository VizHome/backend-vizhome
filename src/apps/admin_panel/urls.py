"""URLs du panel admin interne (staff-only)."""

from __future__ import annotations

from django.urls import path

from apps.support.views import AdminTicketListView

from . import views

urlpatterns = [
    path('overview', views.AdminOverviewView.as_view(), name='admin-overview'),
    # Drill-down users : liste + détail/modération
    path('users', views.AdminUserListView.as_view(), name='admin-users'),
    path('users/<int:pk>', views.AdminUserDetailView.as_view(), name='admin-user-detail'),
    # Drill-down renders : liste
    path('renders', views.AdminRenderListView.as_view(), name='admin-renders'),
    # Séries temporelles pour graphiques (page /admin/analytics)
    path('timeline', views.AdminTimelineView.as_view(), name='admin-timeline'),
    # Audit log des actions admin (qui a fait quoi, quand)
    path('audit-log', views.AdminAuditLogListView.as_view(), name='admin-audit-log'),
    # Billing : subscriptions Stripe actives + invoices récentes
    path(
        'subscriptions',
        views.AdminSubscriptionsView.as_view(),
        name='admin-subscriptions',
    ),
    path('invoices', views.AdminInvoicesView.as_view(), name='admin-invoices'),
    # Forum admin : liste paginée de tous les topics (modération bulk)
    path('forum/topics', views.AdminForumTopicsView.as_view(), name='admin-forum-topics'),
    # Support admin : liste paginée de tous les tickets (modération staff)
    path('support/tickets', AdminTicketListView.as_view(), name='admin-support-tickets'),
]
