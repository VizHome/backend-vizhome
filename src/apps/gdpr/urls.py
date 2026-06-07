"""Routing pour l'app gdpr.

Les patterns sont consommés depuis `config/urls.py` et inclus sous
`/api/v1/me/` (préfixe ajouté au merge avec `accounts.me_patterns`).
"""

from __future__ import annotations

from django.urls import path

from . import views

me_patterns = [
    path('export-data', views.ExportDataView.as_view(), name='export-data'),
    path(
        'export-data/status',
        views.ExportDataStatusView.as_view(),
        name='export-data-status',
    ),
    path(
        'delete-account',
        views.RequestDeleteAccountView.as_view(),
        name='delete-account',
    ),
    path(
        'delete-account/cancel',
        views.CancelDeleteAccountView.as_view(),
        name='delete-account-cancel',
    ),
]
