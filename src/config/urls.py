"""Root URL configuration for VizHome backend.

API endpoints are versioned under /api/v1/. Each app exposes its own urls.py
that gets included here as it comes online.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.accounts.urls import auth_patterns, me_patterns
from apps.billing.urls import me_patterns as billing_me_patterns
from apps.billing.urls import public_patterns as billing_public_patterns
from apps.projects.views import SharedProjectView

# Merge billing endpoints dans /me/ pour rester cohérent avec le frontend
all_me_patterns = me_patterns + billing_me_patterns

api_v1_patterns: list = [
    path('auth/', include((auth_patterns, 'auth'))),
    path('me/', include((all_me_patterns, 'me'))),
    path('billing/', include((billing_public_patterns, 'billing'))),
    path('renders/', include('apps.renders.urls')),
    path('projects/', include('apps.projects.urls')),
    path('forum/', include('apps.forum.urls')),
    path('support/', include('apps.support.urls')),
    path('admin/', include('apps.admin_panel.urls')),
    # Endpoint public (pas d'auth) — accès à un projet via share token
    path('shared/<str:token>', SharedProjectView.as_view(), name='shared-project'),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include((api_v1_patterns, 'api_v1'))),
    # Webhook Stripe — pris en charge par dj-stripe (signature validation incluse)
    path('webhooks/stripe/', include('djstripe.urls', namespace='djstripe')),
    # Healthcheck (liveness + readiness) — pour Docker / load balancers
    path('health/', include('apps.core.urls')),
    # OpenAPI schema + UIs (Swagger + Redoc)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Sert les fichiers media en dev (en prod c'est nginx/S3)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
