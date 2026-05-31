"""URLs du panel admin interne (staff-only)."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path('overview', views.AdminOverviewView.as_view(), name='admin-overview'),
    # Drill-down users : liste + détail/modération
    path('users', views.AdminUserListView.as_view(), name='admin-users'),
    path('users/<int:pk>', views.AdminUserDetailView.as_view(), name='admin-user-detail'),
    # Drill-down renders : liste
    path('renders', views.AdminRenderListView.as_view(), name='admin-renders'),
]
