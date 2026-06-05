"""Vues DRF de l'app projects."""

from __future__ import annotations

import secrets

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


from .models import (
    Annotation,
    ImportedModel,
    Project,
    Scene,
    ShareLink,
)
from .permissions import IsProjectOwner
from .presigned import generate_upload_url, head_object
from .serializers import (
    AnnotationSerializer,
    ImportedModelSerializer,
    ImportedModelUpdateSerializer,
    ImportedModelUploadSerializer,
    PresignedUploadConfirmSerializer,
    PresignedUploadRequestSerializer,
    ProjectCreateUpdateSerializer,
    ProjectDetailSerializer,
    ProjectListSerializer,
    SceneSerializer,
    ShareLinkCreateSerializer,
    ShareLinkSerializer,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_owned_project(user, pk: int) -> Project:
    return get_object_or_404(Project, pk=pk, user=user)


# ─── Project ──────────────────────────────────────────────────────────────────
class ProjectListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateUpdateSerializer
        return ProjectListSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        project = Project.objects.get(pk=serializer.instance.pk)
        output = ProjectDetailSerializer(project, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsProjectOwner]

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return ProjectCreateUpdateSerializer
        return ProjectDetailSerializer


class ProjectDuplicateView(APIView):
    """POST /projects/{id}/duplicate[?copy_assets=true]

    Par défaut, copie : projet + scene + annotations.
    Avec ?copy_assets=true, copie aussi les modèles 3D via copy_object MinIO
    (server-side, rapide, mais incrémente le storage usage).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        original = get_owned_project(request.user, pk)
        copy_assets = request.query_params.get("copy_assets", "").lower() in (
            "true",
            "1",
            "yes",
        )

        # Vérif quota AVANT toute opération si on copie les assets
        if copy_assets:
            total_size = sum(m.file_size_bytes for m in original.imported_models.all())
            stats = request.user.stats
            if stats.storage_used_bytes + total_size > stats.storage_limit_bytes:
                return Response(
                    {
                        "detail": (
                            f"Quota storage dépassé pour cette duplication "
                            f"({total_size} octets requis)."
                        ),
                        "code": "storage_exceeded",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        new_project = Project.objects.create(
            user=request.user,
            title=f"{original.title} (copie)",
            description=original.description,
        )

        # Scene (créée auto via signal)
        new_project.scene.data = dict(original.scene.data)
        new_project.scene.save()

        # Annotations
        for ann in original.annotations.all():
            Annotation.objects.create(
                project=new_project,
                type=ann.type,
                position=ann.position,
                content=ann.content,
                color=ann.color,
            )

        # Modèles 3D — optionnel
        if copy_assets:
            self._copy_imported_models(original, new_project)

        return Response(
            ProjectDetailSerializer(new_project, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _copy_imported_models(original: Project, new_project: Project) -> None:
        """Copie server-side des modèles 3D via MinIO copy_object."""
        import secrets

        from .presigned import copy_object

        for original_model in original.imported_models.all():
            # Génère une nouvelle key avec un suffix aléatoire pour éviter collision
            original_key = original_model.file.name
            ext = original_key.rsplit(".", 1)[-1]
            new_key = (
                f"projects/models/{timezone.now():%Y/%m}/"
                f"{new_project.pk}_{secrets.token_urlsafe(12)}.{ext}"
            )
            copy_object(original_key, new_key)

            # Idem pour le MTL si présent
            new_mtl_key = ""
            if original_model.mtl_file:
                mtl_ext = original_model.mtl_file.name.rsplit(".", 1)[-1]
                new_mtl_key = (
                    f"projects/models/{timezone.now():%Y/%m}/"
                    f"{new_project.pk}_{secrets.token_urlsafe(12)}.{mtl_ext}"
                )
                copy_object(original_model.mtl_file.name, new_mtl_key)

            ImportedModel.objects.create(
                project=new_project,
                name=original_model.name,
                format=original_model.format,
                file=new_key,
                mtl_file=new_mtl_key or None,
                file_size_bytes=original_model.file_size_bytes,
                position=dict(original_model.position),
                rotation=dict(original_model.rotation),
                scale=dict(original_model.scale),
            )


# ─── Scene ────────────────────────────────────────────────────────────────────
class SceneView(generics.RetrieveUpdateAPIView):
    """GET /projects/{id}/scene — lit le JSON state Three.js
    PUT /projects/{id}/scene — sauvegarde complète (incrémente la version).
    """

    serializer_class = SceneSerializer
    permission_classes = [IsAuthenticated, IsProjectOwner]

    def get_object(self) -> Scene:
        project = get_owned_project(self.request.user, self.kwargs["pk"])
        self.check_object_permissions(self.request, project)
        return project.scene

    def perform_update(self, serializer):
        scene = serializer.save()
        scene.version = scene.version + 1
        scene.save(update_fields=["version", "updated_at"])


# ─── ImportedModel ────────────────────────────────────────────────────────────
class ImportedModelListCreateView(APIView):
    """POST /projects/{id}/models — upload multipart classique (< 10MB).
    GET — liste tous les modèles du projet.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        project = get_owned_project(request.user, pk)
        models = project.imported_models.all()
        return Response(
            ImportedModelSerializer(
                models, many=True, context={"request": request}
            ).data
        )

    def post(self, request: Request, pk: int) -> Response:
        project = get_owned_project(request.user, pk)
        serializer = ImportedModelUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["file"]
        mtl_file = serializer.validated_data.get("mtl_file")
        total_size = file.size + (mtl_file.size if mtl_file else 0)

        # Vérif quota storage
        stats = request.user.stats
        if stats.storage_used_bytes + total_size > stats.storage_limit_bytes:
            return Response(
                {"detail": "Quota storage dépassé.", "code": "storage_exceeded"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext = file.name.rsplit(".", 1)[-1].lower()
        imported = ImportedModel.objects.create(
            project=project,
            name=serializer.validated_data["name"],
            format=ext,
            file=file,
            mtl_file=mtl_file,
            file_size_bytes=total_size,
        )
        return Response(
            ImportedModelSerializer(imported, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ImportedModelDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /projects/{pk}/models/{model_id}."""

    permission_classes = [IsAuthenticated, IsProjectOwner]
    lookup_url_kwarg = "model_id"

    def get_queryset(self):
        return ImportedModel.objects.filter(
            project__user=self.request.user, project_id=self.kwargs["pk"]
        )

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return ImportedModelUpdateSerializer
        return ImportedModelSerializer


# ─── Presigned upload (gros fichiers) ─────────────────────────────────────────
class PresignedUploadView(APIView):
    """POST /projects/{id}/models/upload-url
    Renvoie une URL pré-signée pour PUT direct du fichier vers MinIO.
    Le frontend doit ensuite appeler /confirm pour enregistrer en DB.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        project = get_owned_project(request.user, pk)
        serializer = PresignedUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        size = serializer.validated_data["file_size_bytes"]
        stats = request.user.stats
        if stats.storage_used_bytes + size > stats.storage_limit_bytes:
            return Response(
                {"detail": "Quota storage dépassé.", "code": "storage_exceeded"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Génère une clé S3 unique
        file_name = serializer.validated_data["file_name"]
        ext = file_name.rsplit(".", 1)[-1].lower()
        key = (
            f"projects/models/{timezone.now():%Y/%m}/"
            f"{project.pk}_{secrets.token_urlsafe(12)}.{ext}"
        )

        url = generate_upload_url(
            key=key,
            content_type=serializer.validated_data["content_type"],
        )
        return Response(
            {
                "upload_url": url,
                "key": key,
                "expires_in": 3600,
                "method": "PUT",
                "headers": {"Content-Type": serializer.validated_data["content_type"]},
            }
        )


class PresignedUploadConfirmView(APIView):
    """POST /projects/{id}/models/confirm
    Appelé après l'upload PUT direct par le frontend. Vérifie que le fichier
    existe bien sur MinIO et crée l'ImportedModel.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        project = get_owned_project(request.user, pk)
        serializer = PresignedUploadConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        key = serializer.validated_data["key"]

        # Vérifie la présence et récupère la taille via S3 HEAD
        meta = head_object(key)
        if meta is None:
            return Response(
                {"detail": f"Fichier introuvable sur le storage : {key}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        size = int(meta.get("ContentLength", 0))

        mtl_key = serializer.validated_data.get("mtl_key") or ""
        mtl_size = 0
        if mtl_key:
            mtl_meta = head_object(mtl_key)
            if mtl_meta is None:
                return Response(
                    {"detail": f"MTL introuvable : {mtl_key}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            mtl_size = int(mtl_meta.get("ContentLength", 0))

        total = size + mtl_size
        stats = request.user.stats
        if stats.storage_used_bytes + total > stats.storage_limit_bytes:
            # Trop tard : le fichier est déjà sur MinIO. On le supprime.
            from .presigned import get_internal_client
            from django.conf import settings as dj_settings

            client = get_internal_client()
            client.delete_object(Bucket=dj_settings.AWS_STORAGE_BUCKET_NAME, Key=key)
            if mtl_key:
                client.delete_object(
                    Bucket=dj_settings.AWS_STORAGE_BUCKET_NAME, Key=mtl_key
                )
            return Response(
                {"detail": "Quota storage dépassé.", "code": "storage_exceeded"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext = key.rsplit(".", 1)[-1].lower()
        imported = ImportedModel.objects.create(
            project=project,
            name=serializer.validated_data["name"],
            format=ext,
            file=key,  # FileField accepte une key string (path dans storage)
            mtl_file=mtl_key or None,
            file_size_bytes=total,
        )
        return Response(
            ImportedModelSerializer(imported, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# ─── Annotation ───────────────────────────────────────────────────────────────
class AnnotationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AnnotationSerializer

    def get_queryset(self):
        return Annotation.objects.filter(
            project__user=self.request.user, project_id=self.kwargs["pk"]
        )

    def perform_create(self, serializer):
        project = get_owned_project(self.request.user, self.kwargs["pk"])
        serializer.save(project=project)


class AnnotationDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AnnotationSerializer
    lookup_url_kwarg = "annotation_id"

    def get_queryset(self):
        return Annotation.objects.filter(
            project__user=self.request.user, project_id=self.kwargs["pk"]
        )


# ─── ShareLink ────────────────────────────────────────────────────────────────
class ShareLinkListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ShareLink.objects.filter(
            project__user=self.request.user, project_id=self.kwargs["pk"]
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ShareLinkCreateSerializer
        return ShareLinkSerializer

    def perform_create(self, serializer):
        project = get_owned_project(self.request.user, self.kwargs["pk"])
        serializer.save(project=project, created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        out = ShareLinkSerializer(serializer.instance, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)


class ShareLinkDetailView(generics.DestroyAPIView):
    """Suppression d'un share link (révocation)."""

    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "share_id"

    def get_queryset(self):
        return ShareLink.objects.filter(
            project__user=self.request.user, project_id=self.kwargs["pk"]
        )


class SharedProjectView(APIView):
    """GET /shared/{token} — accès public au projet via token.

    Pas d'auth requise. Renvoie la version read-only complète du projet.
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # désactive JWT auth pour ce endpoint public

    def get(self, request: Request, token: str) -> Response:
        try:
            link = ShareLink.objects.select_related("project").get(token=token)
        except ShareLink.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if link.is_expired:
            return Response(
                {"detail": "Ce lien de partage a expiré.", "code": "expired"},
                status=status.HTTP_410_GONE,
            )

        # Marque l'utilisation
        link.last_used_at = timezone.now()
        link.save(update_fields=["last_used_at"])

        return Response(
            ProjectDetailSerializer(link.project, context={"request": request}).data
        )


# ─── Thumbnail upload ──────────────────────────────────────────────────────
class ProjectThumbnailView(APIView):
    """POST /projects/{id}/thumbnail — upload une miniature pour le projet.

    Reçoit une image (JPEG/PNG/WebP, max 1 Mo) au format multipart, l'écrit
    dans `Project.thumbnail` (ImageField → MinIO/MEDIA_ROOT selon storage),
    retourne le ProjectDetail avec l'URL mise à jour.

    Le frontend appelle cet endpoint juste après le save de la scène, avec
    un blob généré via `canvas.toDataURL('image/jpeg', 0.7)` ré-encodé en
    400×300 sur un canvas off-screen.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    MAX_SIZE = 1 * 1024 * 1024  # 1 Mo (largement assez pour 400×300 JPEG q=0.7)
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def post(self, request: Request, pk: int) -> Response:
        project = get_owned_project(request.user, pk)

        file = request.FILES.get("thumbnail")
        if not file:
            return Response(
                {
                    "detail": "Le champ `thumbnail` (fichier image) est requis.",
                    "code": "missing_file",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size > self.MAX_SIZE:
            return Response(
                {
                    "detail": f"Image trop volumineuse (max {self.MAX_SIZE // 1024} Ko).",
                    "code": "too_large",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.content_type not in self.ALLOWED_CONTENT_TYPES:
            return Response(
                {
                    "detail": "Format non supporté (JPEG/PNG/WebP uniquement).",
                    "code": "invalid_format",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Supprime l'ancien thumbnail si présent (évite l'orphelin sur MinIO)
        if project.thumbnail:
            project.thumbnail.delete(save=False)

        # Ré-extension propre pour MinIO
        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
            file.content_type
        ]
        file.name = f"thumb-{project.pk}.{ext}"

        project.thumbnail = file
        project.save(update_fields=["thumbnail", "updated_at"])

        return Response(
            ProjectDetailSerializer(project, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
