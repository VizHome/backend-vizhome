"""URL routing pour l'app accounts.

Le module expose deux listes de routes incluses sous `auth/` et `me/` depuis
config/urls.py.
"""
from __future__ import annotations

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import two_factor, views
from .oauth.views import OAuthExchangeView

auth_patterns = [
    path('register', views.RegisterView.as_view(), name='register'),
    path('login', views.LoginView.as_view(), name='login'),
    path('refresh', TokenRefreshView.as_view(), name='refresh'),
    path('logout', views.LogoutView.as_view(), name='logout'),
    path('forgot-password', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password', views.ResetPasswordView.as_view(), name='reset-password'),
    # 2FA — étape 2 du login
    path('2fa/verify', two_factor.Verify2FALoginView.as_view(), name='2fa-verify-login'),
    # OAuth
    path('oauth/<str:provider>/exchange', OAuthExchangeView.as_view(), name='oauth-exchange'),
]

me_patterns = [
    path('', views.MeView.as_view(), name='me'),
    path('preferences', views.PreferencesView.as_view(), name='preferences'),
    path('change-password', views.ChangePasswordView.as_view(), name='change-password'),
    path('sessions', views.SessionListView.as_view(), name='sessions'),
    path('sessions/<int:pk>', views.SessionDetailView.as_view(), name='session-detail'),
    # 2FA — gestion par le user authentifié
    path('2fa/setup', two_factor.Setup2FAView.as_view(), name='2fa-setup'),
    path('2fa/verify-setup', two_factor.VerifySetup2FAView.as_view(), name='2fa-verify-setup'),
    path('2fa/disable', two_factor.Disable2FAView.as_view(), name='2fa-disable'),
]
