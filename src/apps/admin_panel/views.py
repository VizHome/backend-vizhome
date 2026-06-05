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

from rest_framework.renderers import JSONRenderer

from .audit import log_admin_action
from .models import AdminAuditLog
from .renderers import CSVRenderer
from .serializers import (
    AdminAuditLogSerializer,
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

        return Response(
            {
                "generated_at": now.isoformat(),
                "users": self._users(today_start, week_start, month_start),
                "sessions": self._sessions(),
                "renders": self._renders(month_start),
                "projects": self._projects(),
                "storage": self._storage(),
                "billing": self._billing(),
                "forum": self._forum(),
                "system": self._system(),
            }
        )

    # ─── Section users ──────────────────────────────────────────────────
    def _users(self, today_start, week_start, month_start) -> dict[str, Any]:
        qs = User.objects.all()
        by_plan = dict(
            qs.values_list("plan").annotate(c=Count("id")).values_list("plan", "c")
        )
        two_factor_enabled = qs.filter(preferences__two_factor_enabled=True).count()
        return {
            "total": qs.count(),
            "new_today": qs.filter(date_joined__gte=today_start).count(),
            "new_this_week": qs.filter(date_joined__gte=week_start).count(),
            "new_this_month": qs.filter(date_joined__gte=month_start).count(),
            "by_plan": by_plan,
            "two_factor_enabled": two_factor_enabled,
            "staff_count": qs.filter(is_staff=True).count(),
            # Top 5 nouveaux users (pour affichage tableau)
            "recent": list(
                qs.order_by("-date_joined")[:5].values(
                    "id",
                    "email",
                    "first_name",
                    "last_name",
                    "plan",
                    "is_staff",
                    "date_joined",
                )
            ),
        }

    # ─── Section sessions actives ───────────────────────────────────────
    def _sessions(self) -> dict[str, Any]:
        active = UserSession.objects.filter(revoked_at__isnull=True)
        return {
            "total_active": active.count(),
            "unique_users_active": active.values("user").distinct().count(),
        }

    # ─── Section renders IA ─────────────────────────────────────────────
    def _renders(self, month_start) -> dict[str, Any]:
        qs = Render.objects.all()
        total = qs.count()
        by_status = dict(
            qs.values_list("status").annotate(c=Count("id")).values_list("status", "c")
        )
        by_source = dict(
            qs.values_list("source").annotate(c=Count("id")).values_list("source", "c")
        )
        done = by_status.get(Render.Status.DONE, 0)
        # Success rate = done / (done + failed), arrondi à 3 décimales
        terminal = done + by_status.get(Render.Status.FAILED, 0)
        success_rate = round(done / terminal, 3) if terminal else None

        return {
            "total": total,
            "this_month": qs.filter(created_at__gte=month_start).count(),
            "by_status": by_status,
            "by_source": by_source,
            "success_rate": success_rate,
            # 5 derniers renders (toutes statuts confondus)
            "recent": list(
                qs.select_related("user")
                .order_by("-created_at")[:5]
                .values(
                    "id",
                    "status",
                    "source",
                    "output_type",
                    "provider",
                    "created_at",
                    "user__email",
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
            ImportedModel.objects.values("project")
            .aggregate(avg=Count("id") / max(total, 1))
            .get("avg", 0)
        )
        return {
            "total": total,
            "archived": qs.filter(is_archived=True).count(),
            "with_scene": with_scene,
            "avg_models_per_project": (
                round(ImportedModel.objects.count() / total, 2) if total else 0
            ),
        }

    # ─── Section storage MinIO ──────────────────────────────────────────
    def _storage(self) -> dict[str, Any]:
        stats = User.objects.aggregate(total=Sum("stats__storage_used_bytes"))
        total_bytes = stats["total"] or 0
        # Top 10 utilisateurs par usage storage
        top_users = list(
            User.objects.filter(stats__storage_used_bytes__gt=0)
            .order_by("-stats__storage_used_bytes")[:10]
            .values("id", "email", "plan")
            .annotate(bytes=Sum("stats__storage_used_bytes"))
        )
        return {
            "total_bytes": total_bytes,
            "top_users": top_users,
        }

    # ─── Section billing (Stripe via User.plan) ─────────────────────────
    def _billing(self) -> dict[str, Any]:
        # MRR estimé depuis User.plan + PLAN_CONFIG (les plans payants ont
        # un price_eur en cents). Source de vérité = Stripe webhooks qui
        # synchronisent User.plan via apps.billing.handlers.
        billable = User.objects.exclude(plan="free")
        paying = billable.count()
        mrr_cents = sum(
            PLAN_CONFIG.get(u.plan, {}).get("price_eur", 0) or 0 for u in billable
        )
        return {
            "paying_users": paying,
            "mrr_eur": round(mrr_cents / 100, 2),
            "mrr_cents": mrr_cents,
            "by_plan": dict(
                billable.values_list("plan")
                .annotate(c=Count("id"))
                .values_list("plan", "c")
            ),
        }

    # ─── Section forum ──────────────────────────────────────────────────
    def _forum(self) -> dict[str, Any]:
        return {
            "categories": ForumCategory.objects.count(),
            "topics": ForumTopic.objects.count(),
            "replies": ForumReply.objects.count(),
            "uploads_total": ForumUpload.objects.count(),
            "uploads_orphan": ForumUpload.objects.filter(used=False).count(),
            "pinned_topics": ForumTopic.objects.filter(is_pinned=True).count(),
            "locked_topics": ForumTopic.objects.filter(is_locked=True).count(),
            "recent_topics": list(
                ForumTopic.objects.select_related("author", "category")
                .order_by("-created_at")[:5]
                .values(
                    "id",
                    "title",
                    "created_at",
                    "replies_count",
                    "views_count",
                    "is_pinned",
                    "is_locked",
                    "author__email",
                    "category__name",
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
            "gemini_configured": bool(getattr(settings, "GEMINI_API_KEY", "")),
            "stripe_configured": stripe_ok,
            "google_oauth_configured": bool(
                getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
            ),
            "github_oauth_configured": bool(
                getattr(settings, "GITHUB_OAUTH_CLIENT_ID", "")
            ),
            "minio_configured": bool(
                getattr(settings, "AWS_ACCESS_KEY_ID", "")
                and getattr(settings, "AWS_S3_CUSTOM_DOMAIN", "")
            ),
            "sentry_configured": bool(getattr(settings, "SENTRY_DSN", "")),
            "render_provider": getattr(settings, "RENDERS_DEFAULT_PROVIDER", "gemini"),
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
    - `?format=csv`     : exporte en CSV (téléchargement)
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminUserSerializer
    renderer_classes = [JSONRenderer, CSVRenderer]
    csv_filename = "admin-users"

    def get_queryset(self):
        qs = User.objects.select_related("stats").all()
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        plan = params.get("plan")
        if plan:
            qs = qs.filter(plan=plan)

        for flag in ("is_staff", "is_active"):
            val = params.get(flag)
            if val in ("true", "1"):
                qs = qs.filter(**{flag: True})
            elif val in ("false", "0"):
                qs = qs.filter(**{flag: False})

        ordering = params.get("ordering", "-date_joined")
        allowed = {
            "date_joined",
            "-date_joined",
            "email",
            "-email",
            "plan",
            "-plan",
            "last_login",
            "-last_login",
        }
        return qs.order_by(ordering if ordering in allowed else "-date_joined")


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/admin/users/{id} — détail + modération (ban/unban, staff)."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        return User.objects.select_related("stats").all()

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        # Garde-fou : un admin ne peut pas se rétrograder lui-même
        # (sinon plus aucun staff dans l'app potentiellement).
        if instance.pk == request.user.pk:
            if "is_staff" in request.data and not request.data["is_staff"]:
                return Response(
                    {
                        "detail": "Tu ne peux pas retirer ton propre rôle staff.",
                        "code": "self_demotion_forbidden",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "is_active" in request.data and not request.data["is_active"]:
                return Response(
                    {
                        "detail": "Tu ne peux pas désactiver ton propre compte.",
                        "code": "self_deactivation_forbidden",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Snapshot avant/après pour l'audit log
        before = {
            "is_active": instance.is_active,
            "is_staff": instance.is_staff,
            "is_banned_from_forum": instance.is_banned_from_forum,
            "pseudo": instance.pseudo,
        }
        response = super().update(request, *args, **kwargs)
        instance.refresh_from_db()
        after = {
            "is_active": instance.is_active,
            "is_staff": instance.is_staff,
            "is_banned_from_forum": instance.is_banned_from_forum,
            "pseudo": instance.pseudo,
        }

        # Log uniquement les changements effectifs (pas une PATCH no-op)
        if before["is_active"] != after["is_active"]:
            log_admin_action(
                request,
                (
                    AdminAuditLog.Action.USER_BAN
                    if not after["is_active"]
                    else AdminAuditLog.Action.USER_UNBAN
                ),
                target=instance,
                payload={"before": before, "after": after},
            )
        if before["is_staff"] != after["is_staff"]:
            log_admin_action(
                request,
                (
                    AdminAuditLog.Action.USER_PROMOTE_STAFF
                    if after["is_staff"]
                    else AdminAuditLog.Action.USER_DEMOTE_STAFF
                ),
                target=instance,
                payload={"before": before, "after": after},
            )
        if before["is_banned_from_forum"] != after["is_banned_from_forum"]:
            log_admin_action(
                request,
                (
                    AdminAuditLog.Action.USER_BAN_FORUM
                    if after["is_banned_from_forum"]
                    else AdminAuditLog.Action.USER_UNBAN_FORUM
                ),
                target=instance,
                payload={"before": before, "after": after},
            )
        if before["pseudo"] != after["pseudo"]:
            log_admin_action(
                request,
                AdminAuditLog.Action.USER_PSEUDO_CHANGE,
                target=instance,
                payload={"before": before["pseudo"], "after": after["pseudo"]},
            )
        return response


# ─── Timeline : séries temporelles pour graphiques ─────────────────────────
class AdminTimelineView(APIView):
    """GET /api/v1/admin/timeline?days=30

    Retourne des séries temporelles pour les graphiques admin :
    - users_per_day : nouveaux users par jour
    - renders_per_day : renders créés par jour (groupé par status)
    - renders_status_breakdown : distribution actuelle par status (pour donut)

    Query param :
    - `days` : nombre de jours rétrospectifs (défaut 30, max 365)
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, *args, **kwargs) -> Response:
        try:
            days = max(1, min(365, int(request.query_params.get("days", 30))))
        except (TypeError, ValueError):
            days = 30

        now = timezone.now()
        start = (now - timedelta(days=days - 1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        # Bucket bornes : 1 entrée par jour (yyyy-mm-dd)
        days_list = [(start + timedelta(days=i)).date() for i in range(days)]

        # ─── Users / jour ────────────────────────────────────────────────
        users_qs = User.objects.filter(date_joined__gte=start)
        users_count_by_day: dict[str, int] = {d.isoformat(): 0 for d in days_list}
        for u in users_qs.values("date_joined"):
            key = u["date_joined"].date().isoformat()
            if key in users_count_by_day:
                users_count_by_day[key] += 1

        # ─── Renders / jour (par status) ────────────────────────────────
        renders_qs = Render.objects.filter(created_at__gte=start)
        renders_status_by_day: dict[str, dict[str, int]] = {
            d.isoformat(): {
                "pending": 0,
                "processing": 0,
                "done": 0,
                "failed": 0,
            }
            for d in days_list
        }
        for r in renders_qs.values("created_at", "status"):
            key = r["created_at"].date().isoformat()
            if key in renders_status_by_day:
                renders_status_by_day[key][r["status"]] = (
                    renders_status_by_day[key].get(r["status"], 0) + 1
                )

        # ─── Distribution actuelle par status (snapshot pour donut) ─────
        all_renders = Render.objects.values("status").annotate(c=Count("id"))
        renders_status_breakdown = {row["status"]: row["c"] for row in all_renders}

        # ─── Forum activity / jour ──────────────────────────────────────
        topics_qs = ForumTopic.objects.filter(created_at__gte=start).values(
            "created_at"
        )
        replies_qs = ForumReply.objects.filter(created_at__gte=start).values(
            "created_at"
        )
        topics_per_day = {d.isoformat(): 0 for d in days_list}
        replies_per_day = {d.isoformat(): 0 for d in days_list}
        for t in topics_qs:
            k = t["created_at"].date().isoformat()
            if k in topics_per_day:
                topics_per_day[k] += 1
        for r in replies_qs:
            k = r["created_at"].date().isoformat()
            if k in replies_per_day:
                replies_per_day[k] += 1

        return Response(
            {
                "days": days,
                "start": start.isoformat(),
                "end": now.isoformat(),
                "users_per_day": [
                    {"date": k, "count": v} for k, v in users_count_by_day.items()
                ],
                "renders_per_day": [
                    {"date": k, **v} for k, v in renders_status_by_day.items()
                ],
                "renders_status_breakdown": renders_status_breakdown,
                "forum_activity_per_day": [
                    {
                        "date": k,
                        "topics": topics_per_day.get(k, 0),
                        "replies": replies_per_day.get(k, 0),
                    }
                    for k in users_count_by_day  # même ordre que users_per_day
                ],
            }
        )


# ─── Audit log : liste paginée des actions admin ───────────────────────────
class AdminAuditLogListView(generics.ListAPIView):
    """GET /api/v1/admin/audit-log — liste paginée + filtres staff-only.

    Query params :
    - `action=<value>` : filtre par action (ex: user.ban, topic.pin)
    - `actor=<email>`  : filtre par email d'acteur (icontains)
    - `target_type=<X>` : filtre par type de cible (User, Topic, Reply, …)
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminAuditLogSerializer

    def get_queryset(self):
        qs = AdminAuditLog.objects.select_related("actor").all()
        params = self.request.query_params

        action = params.get("action")
        if action:
            qs = qs.filter(action=action)

        actor = params.get("actor", "").strip()
        if actor:
            qs = qs.filter(actor_email__icontains=actor)

        target_type = params.get("target_type")
        if target_type:
            qs = qs.filter(target_type=target_type)

        return qs


# ─── Drill-down : renders ───────────────────────────────────────────────────
class AdminRenderListView(generics.ListAPIView):
    """GET /api/v1/admin/renders — liste paginée + filtres.

    Query params :
    - `?status=<s>`   : pending / processing / done / failed
    - `?source=<s>`   : prompt / sketch / screenshot
    - `?user_id=<n>`  : filtre par auteur
    - `?ordering=...` : -created_at (défaut), created_at, -completed_at
    - `?format=csv`   : exporte en CSV
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = AdminRenderSerializer
    renderer_classes = [JSONRenderer, CSVRenderer]
    csv_filename = "admin-renders"

    def get_queryset(self):
        qs = Render.objects.select_related("user").all()
        params = self.request.query_params

        for field in ("status", "source"):
            val = params.get(field)
            if val:
                qs = qs.filter(**{field: val})

        user_id = params.get("user_id")
        if user_id and user_id.isdigit():
            qs = qs.filter(user_id=int(user_id))

        ordering = params.get("ordering", "-created_at")
        allowed = {
            "created_at",
            "-created_at",
            "completed_at",
            "-completed_at",
        }
        return qs.order_by(ordering if ordering in allowed else "-created_at")


# ─── Billing : subscriptions + invoices (staff drill-down Stripe) ──────────
class AdminSubscriptionsView(APIView):
    """GET /api/v1/admin/subscriptions — liste des subscriptions Stripe actives.

    Lit djstripe `Subscription` directement. Si Stripe n'est pas configuré,
    retourne une liste vide (mode dégradé).
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, *args, **kwargs) -> Response:
        try:
            from djstripe.models import Subscription

            # djstripe stocke status dans stripe_data JSONField selon la version
            # → on récupère tout et filtre en Python (pagination implicite via [:200])
            all_subs = Subscription.objects.all()[:500]
        except Exception as e:
            return Response(
                {
                    "count": 0,
                    "results": [],
                    "mode": "no_djstripe",
                    "detail": str(e),
                }
            )

        active_statuses = {"active", "trialing", "past_due"}
        data = []
        for sub in all_subs:
            # Lire status — peut être direct OU dans stripe_data selon version djstripe
            sub_status = getattr(sub, "status", None) or (sub.stripe_data or {}).get(
                "status", ""
            )
            if sub_status not in active_statuses:
                continue
            row = {"id": str(sub.id), "status": sub_status}
            for attr, key in (
                ("current_period_end", "current_period_end"),
                ("cancel_at_period_end", "cancel_at_period_end"),
                ("created", "created"),
            ):
                try:
                    val = getattr(sub, attr, None)
                    row[key] = val.isoformat() if hasattr(val, "isoformat") else val
                except Exception:
                    row[key] = None
            try:
                cust = getattr(sub, "customer", None)
                subscriber = getattr(cust, "subscriber", None) if cust else None
                row["user_email"] = (
                    getattr(subscriber, "email", "") if subscriber else ""
                )
                row["user_id"] = getattr(subscriber, "pk", None) if subscriber else None
            except Exception:
                row["user_email"] = ""
                row["user_id"] = None
            data.append(row)
        return Response({"count": len(data), "results": data})


class AdminInvoicesView(APIView):
    """GET /api/v1/admin/invoices — 100 dernières factures Stripe.

    Retourne les invoices les plus récentes toutes-confondues.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, *args, **kwargs) -> Response:
        try:
            from djstripe.models import Invoice

            invoices = Invoice.objects.order_by("-created")[:100]
        except Exception as e:
            return Response(
                {
                    "count": 0,
                    "results": [],
                    "mode": "no_djstripe",
                    "detail": str(e),
                }
            )

        data = []
        for inv in invoices:
            row = {
                "id": str(inv.id),
                "number": getattr(inv, "number", "") or "",
                "amount_paid": getattr(inv, "amount_paid", 0) or 0,
                "currency": getattr(inv, "currency", "") or "",
                "status": getattr(inv, "status", "") or "",
                "hosted_invoice_url": getattr(inv, "hosted_invoice_url", "") or "",
                "invoice_pdf": getattr(inv, "invoice_pdf", "") or "",
            }
            try:
                created = getattr(inv, "created", None)
                row["created"] = (
                    created.isoformat() if hasattr(created, "isoformat") else None
                )
            except Exception:
                row["created"] = None
            try:
                cust = getattr(inv, "customer", None)
                subscriber = getattr(cust, "subscriber", None) if cust else None
                row["user_email"] = (
                    getattr(subscriber, "email", "") if subscriber else ""
                )
            except Exception:
                row["user_email"] = ""
            data.append(row)
        return Response({"count": len(data), "results": data})


# ─── Forum admin : liste topics + actions modération ───────────────────────
class AdminForumTopicsView(generics.ListAPIView):
    """GET /api/v1/admin/forum/topics — liste paginée des topics (staff).

    Différent de /forum/topics (publique) : ne filtre rien, retourne aussi
    is_pinned / is_locked / replies_count pour faciliter la modération.

    Query params :
    - `?category=<slug>` : filtre par catégorie
    - `?search=<q>`     : recherche dans le titre
    - `?ordering=...`   : -created_at (défaut), -replies_count, -views_count
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    renderer_classes = [JSONRenderer, CSVRenderer]
    csv_filename = "admin-forum-topics"

    def get_serializer_class(self):
        # Réutilise le serializer public List du forum
        from apps.forum.serializers import TopicListSerializer

        return TopicListSerializer

    def get_queryset(self):
        from apps.forum.models import Topic as ForumTopicModel

        qs = ForumTopicModel.objects.select_related("category", "author").all()
        params = self.request.query_params

        category = params.get("category")
        if category:
            qs = qs.filter(category__slug=category)

        search = params.get("search", "").strip()
        if search:
            qs = qs.filter(title__icontains=search)

        ordering = params.get("ordering", "-created_at")
        allowed = {
            "created_at",
            "-created_at",
            "replies_count",
            "-replies_count",
            "views_count",
            "-views_count",
        }
        return qs.order_by(ordering if ordering in allowed else "-created_at")
