"""URL routing pour l'app forum."""
from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    # Categories (publique en lecture)
    path('categories', views.CategoryListView.as_view(), name='forum-categories'),
    path('categories/<slug:slug>', views.CategoryDetailView.as_view(), name='forum-category-detail'),

    # Topics
    path('topics', views.TopicListCreateView.as_view(), name='forum-topics'),
    path('topics/<int:pk>', views.TopicDetailView.as_view(), name='forum-topic-detail'),

    # Replies — nested under topic
    path('topics/<int:topic_id>/replies', views.ReplyListCreateView.as_view(), name='forum-replies'),
    path('replies/<int:pk>', views.ReplyDetailView.as_view(), name='forum-reply-detail'),

    # Upload image pour insertion dans un post (multipart direct, pas presigned)
    path('upload-image', views.ForumImageUploadView.as_view(), name='forum-upload-image'),
]
