"""URL routing pour l'app projects."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path('', views.ProjectListCreateView.as_view(), name='projects-list'),
    path('<int:pk>', views.ProjectDetailView.as_view(), name='projects-detail'),
    path('<int:pk>/duplicate', views.ProjectDuplicateView.as_view(), name='projects-duplicate'),

    # Scene
    path('<int:pk>/scene', views.SceneView.as_view(), name='projects-scene'),

    # ImportedModel
    path('<int:pk>/models', views.ImportedModelListCreateView.as_view(), name='projects-models'),
    path(
        '<int:pk>/models/upload-url',
        views.PresignedUploadView.as_view(),
        name='projects-models-upload-url',
    ),
    path(
        '<int:pk>/models/confirm',
        views.PresignedUploadConfirmView.as_view(),
        name='projects-models-confirm',
    ),
    path(
        '<int:pk>/models/<int:model_id>',
        views.ImportedModelDetailView.as_view(),
        name='projects-models-detail',
    ),

    # Annotation
    path(
        '<int:pk>/annotations',
        views.AnnotationListCreateView.as_view(),
        name='projects-annotations',
    ),
    path(
        '<int:pk>/annotations/<int:annotation_id>',
        views.AnnotationDetailView.as_view(),
        name='projects-annotations-detail',
    ),

    # ShareLink
    path('<int:pk>/share', views.ShareLinkListCreateView.as_view(), name='projects-share'),
    path(
        '<int:pk>/share/<int:share_id>',
        views.ShareLinkDetailView.as_view(),
        name='projects-share-detail',
    ),
]
