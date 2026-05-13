"""Root URL configuration for VizHome backend.

API endpoints are versioned under /api/v1/. Each app exposes its own urls.py
that gets included here as it comes online.
"""
from django.contrib import admin
from django.urls import include, path

api_v1_patterns: list = [
    # path('auth/', include('apps.accounts.urls.auth')),       # étape 2
    # path('me/', include('apps.accounts.urls.me')),           # étape 2
    # path('projects/', include('apps.projects.urls')),        # étape 4
    # path('renders/', include('apps.renders.urls')),          # étape 3
    # path('billing/', include('apps.billing.urls')),          # étape 5
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include((api_v1_patterns, 'api_v1'))),
]
