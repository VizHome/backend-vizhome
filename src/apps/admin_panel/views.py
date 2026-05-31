"""Panel admin interne — endpoints DRF réservés au staff.

Architecture :
- 1 endpoint consolidé `GET /api/v1/admin/overview` qui retourne TOUTES
  les métriques en 1 réponse. Évite N round-trips depuis le frontend.
- Permission `IsAdminUser` (built-in DRF, checks `user.is_staff`).
- Pas de modèles dédiés — on query directement les apps existantes
  (accounts, projects, renders, billing, forum) en read-only.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserSession
from apps.billing.plans import PLAN_CONFIG
from apps.forum.models import Category as ForumCategory
from apps.forum.models import ForumUpload, Reply as ForumReply, Topic as ForumTopic
from apps.projects.models import ImportedModel, Project
from apps.renders.models import Render

from .serializers import (
    AdminRenderSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
)

User = get_user_model()


class AdminOverviewView(APIView):
    """GET /api/v1/admin/overview — dashboard consolidé pour le staff.

    Agrège users, sessions, renders, projects, storage, billing, forum
    et état des intégrations tierces.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, *args, **kwargs) -> Response:
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        return Response({
            'generated_at': now.isoformat(),
            'users': self._users(today_start, week_start, month_start),
            'sessions': self._sessions(),
            'renders': self._renders(month_start),
            'projects': self._projects(),
            'storage': self._storage(),
            'billing': self._billing(),
            'forum': self._forum(),
            'system': self._system(),
        })

    # ─── Section users ──────────────────────────────────────────────────
    def _users(self, today_start, week_start, month_start) -> dict[str, Any]:
        qs = User.objects.all()
        by_plan = dict(
            qs.values_list('plan').annotate(c=Count('id')).values_list('plan', 'c')
        )
        two_factor_enabled = qs.filter(preferences__two_factor_enabled=True).count()
        return {
            'total': qs.count(),
            'new_today': qs.filter(date_joined__gte=today_start).count(),
            'new_this_week': qs.filter(date_joined__gte=week_start).count(),
            'new_this_month': qs.filter(date_joined__gte=month_start).count(),
            'by_plan': by_plan,
            'two_factor_enabled': two_factor_enabled,
            'staff_count': qs.filter(is_staff=True).count(),
            # Top 5 nouveaux users (pour affichage tableau)
            'recent': list(
                qs.order_by('-date_joined')[:5]
                .values('id', 'email', 'first_name', 'last_name', 'plan',
                        'is_staff', 'date_joined')
            ),
        }

    # ─── Section sessions actives ───────────────────────────────────────
    def _sessions(self) -> dict[str, Any]:
        active = UserSession.objects.filter(revoked_at__isnull=True)
        return {
            'total_active': active.count(),
            'unique_users_active': active.values('user').distinct().count(),
        }

    # ─── Section renders IA ─────────────────────────────────────────────
    def _renders(self, month_start) -> dict[str, Any]:
        qs = Render.objects.all()
        total = qs.count()
        by_status = dict(
            qs.values_list('status').annotate(c=Count('id')).values_list('status', 'c')
        )
        by_source = dict(
            qs.values_list('source').annotate(c=Count('id')).values_list('source', 'c')
        )
        done = by_status.get(Render.Status.DONE, 0)
        # Success rate = done / (done + failed), arrondi à 3 décimales
        terminal = done + by_status.get(Render.Status.FAILED, 0)
        success_rate = round(done / terminal, 3) if terminal else None

        return {
            'total': total,
            'this_month': qs.filter(created_at__gte=month_start).count(),
            'by_status': by_status,
            'by_source': by_source,
            'success_rate': success_rate,
            # 5 derniers renders (toutes statuts confondus)
            'recent': list(
                qs.select_related('user').order_by('-created_at')[:5].values(
                    'id', 'status', 'source', 'output_type', 'provider',
                    'created_at', 'user__email',
                )
            ),
        }

    # ─── Section projets ────────────────────────────────────────────────
    def _projects(self) -> dict[str, Any]:
        qs = Project.objects.all()
        total = qs.count()
        with_scene = qs.filter(scene__isnull=False).count()
        # Avg models par projet (incl. projets vides)
        avg_models = (
            ImportedModel.objects.values('project')
            .aggregate(avg=Count('id') / max(total, 1))
            .get('avg', 0)
        )
        return {
            'total': total,
            'archived': qs.filter(is_archived=True).count(),
            'with_scene': with_scene,
            'avg_models_per_project': round(
                ImportedModel.objects.count() / total, 2
            ) if total else 0,
        }

    # ─── Section storage MinIO ──────────────────────────────────────────
    def _storage(self) -> dict[str, Any]:
        stats = User.objects.aggregate(total=Sum('stats__storage_used_bytes'))
        total_bytes = stats['total'] or 0
        # Top 10 utilisateurs par usage storage
        top_users = list(
            User.objects.filter(stats__storage_used_bytes__gt=0)
            .order_by('-stats__storage_used_bytes')[:10]
            .values('id', 'email', 'plan')
            .annotate(bytes=Sum('stats__storage_used_bytes'))
        )
        return {
            'total_bytes': total_bytes,
            'top_users': top_users,
        }

    # ─── Section billing (Stripe via User.plan) ─────────────────────────
    def _billing(self) -> dict[str, Any]:
        # MRR estimé depuis User.plan + PLAN_CONFIG (les plans payants ont
        # un price_eur en cents). Source de vérité = Stripe webhooks qui
        # synchronisent User.plan via apps.billing.handlers.
        billable = User.objects.exclude(plan='free')
        paying = billable.count()
        mrr_cents = sum(
            PLAN_CONFIG.get(u.plan, {}).get('price_eur', 0) or 0
            for u in billable
        )
        return {
            'paying_users': paying,
            'mrr_eur': round(mrr_cents / 100, 2),
            'mrr_cents': mrr_cents,
            'by_plan': dict(
                billable.values_list('plan').annotate(c=Count('id'))
                .values_list('plan', 'c')
            ),
        }

    # ─── Section forum ──────────────────────────────────────────────────
    def _forum(self) -> dict[str, Any]:
        return {
            'categories': ForumCategory.objects.count(),
            'topics': ForumTopic.objects.count(),
            'replies': ForumReply.objects.count(),
            'uploads_total': ForumUpload.objects.count(),
            'uploads_orphan': ForumUpload.objects.filter(used=False).count(),
            'pinned_topics': ForumTopic.objects.filter(is_pinned=True).count(),
            'locked_topics': ForumTopic.objects.filter(is_locked=True).count(),
            'recent_topics': list(
                ForumTopic.objects.select_related('author', 'category')
                .order_by('-created_at')[:5].values(
                    'id', 'title', 'created_at', 'replies_count',
                    'views_count', 'is_pinned', 'is_locked',
                    'author__email', 'category__name',
                )
            ),
        }

    # ─── Section system (intégrations tierces) ──────────────────────────
    def _system(self) -> dict[str, Any]:
        from django.conf import settings

        # Stripe
        try:
            from apps.billing.stripe_client import is_configured as stripe_configured
            stripe_ok = stripe_configured()
        except Exception:
            stripe_ok = False

        return {
            'gemini_configured': bool(getattr(settings, 'GEMINI_API_KEY', '')),
            'stripe_configured': stripe_ok,
            'google_oauth_configured': bool(
                getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
            ),
            'github_oauth_configured': bool(
                getattr(settings, 'GITHUB_OAUTH_CLIENT_ID', '')
            ),
            'minio_configured': bool(
                getattr(settings, 'AWS_ACCESS_KEY_ID', '')
                and getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '')
            ),
            'sentry_configured': bool(getattr(settings, 'SENTRY_DSN', '')),
            'render_provider': getattr(settings, 'RENDERS_DEFAULT_PROVIDER', 'gemini'),
        }


# ─── Drill-down : users ─────────────────────────────────────────────────────
class AdminUserListView(generics.ListAPIView):
    """GET /api/v1/admin/users — liste paginée + filtres.

    Query params :
    - `?search=<q>`     : recherche email / first_name / last_name (icontains)
    - `?plan=<plan>`    : filtre par plan (free / pro / enterprise)
    - `?is_staff=true|false`
    - `?is_active=true|false`
    - `?ordering=...`   : -date_joined (défaut), date_joined, email, plan, last_login
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.select_related('stats').all()
        params = self.request.query_params

        search = params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        plan = params.get('plan')
        if plan:
            qs = qs.filter(plan=plan)

        for flag in ('is_staff', 'is_active'):
            val = params.get(flag)
            if val in ('true', '1'):
                qs = qs.filter(**{flag: True})
            elif val in ('false', '0'):
                qs = qs.filter(**{flag: False})

        ordering = params.get('ordering', '-date_joined')
        allowed = {
            'date_joined', '-date_joined',
            'email', '-email',
            'plan', '-plan',
            'last_login', '-last_login',
        }
        return qs.order_by(ordering if ordering in allowed else '-date_joined')


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/admin/users/{id} — détail + modération (ban/unban, staff)."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return User.objects.select_related('stats').all()

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        # Garde-fou : un admin ne peut pas se rétrograder lui-même
        # (sinon plus aucun staff dans l'app potentiellement).
        if instance.pk == request.user.pk:
            if 'is_staff' in request.data and not request.data['is_staff']:
                return Response(
                    {
                        'detail': "Tu ne peux pas retirer ton propre rôle staff.",
                        'code': 'self_demotion_forbidden',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if 'is_active' in request.data and not request.data['is_active']:
                return Response(
                    {
                        'detail': "Tu ne peux pas désactiver ton propre compte.",
                        'code': 'self_deactivation_forbidden',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().update(request, *args, **kwargs)


# ─── Drill-down : renders ───────────────────────────────────────────────────
class AdminRenderListView(generics.ListAPIView):
    """GET /api/v1/admin/renders — liste paginée + filtres.

    Query params :
    - `?status=<s>`   : pending / processing / done / failed
    - `?source=<s>`   : prompt / sketch / screenshot
    - `?user_id=<n>`  : filtre par auteur
    - `?ordering=...` : -created_at (défaut), created_at, -completed_at
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminRenderSerializer

    def get_queryset(self):
        qs = Render.objects.select_related('user').all()
        params = self.request.query_params

        for field in ('status', 'source'):
            val = params.get(field)
            if val:
                qs = qs.filter(**{field: val})

        user_id = params.get('user_id')
        if user_id and user_id.isdigit():
            qs = qs.filter(user_id=int(user_id))

        ordering = params.get('ordering', '-created_at')
        allowed = {
            'created_at', '-created_at',
            'completed_at', '-completed_at',
        }
        return qs.order_by(ordering if ordering in allowed else '-created_at')
