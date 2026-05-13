"""Root URL configuration for VizHome backend.

API endpoints are versioned under /api/v1/. Each app exposes its own urls.py
that gets included here as it comes online.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts.urls import auth_patterns, me_patterns

api_v1_patterns: list = [
    path('auth/', include((auth_patterns, 'auth'))),
    path('me/', include((me_patterns, 'me'))),
    path('renders/', include('apps.renders.urls')),
    # path('projects/', include('apps.projects.urls')),        # étape 4
    # path('billing/', include('apps.billing.urls')),          # étape 5
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include((api_v1_patterns, 'api_v1'))),
]

# Sert les fichiers media en dev (en prod c'est nginx/S3)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
