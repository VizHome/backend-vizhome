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

    # Actions modération (staff ou owner du topic selon le cas)
    path('topics/<int:pk>/toggle-pin', views.TopicTogglePinView.as_view(), name='forum-topic-toggle-pin'),
    path('topics/<int:pk>/toggle-lock', views.TopicToggleLockView.as_view(), name='forum-topic-toggle-lock'),
    path('replies/<int:pk>/toggle-solution', views.ReplyToggleSolutionView.as_view(), name='forum-reply-toggle-solution'),

    # Upload image pour insertion dans un post (multipart direct, pas presigned)
    path('upload-image', views.ForumImageUploadView.as_view(), name='forum-upload-image'),
]
