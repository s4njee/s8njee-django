from django.urls import path
from . import views

urlpatterns = [
    # App-level URL names are what reverse(), {% url %}, feeds, and tests target.
    path('editor/posts/new/', views.PostEditorView.as_view(), name='post_editor_new'),
    path('editor/posts/preview/', views.PostEditorPreviewView.as_view(), name='post_editor_preview'),
    path('editor/posts/images/', views.PostEditorImageUploadView.as_view(), name='post_editor_image_upload'),
    path('editor/posts/<slug:slug>/', views.PostEditorView.as_view(), name='post_editor_edit'),
    path('', views.PostListView.as_view(), name='post_list'),
    path('archive/<int:year>/<int:month>/', views.PostMonthArchiveView.as_view(), name='post_archive_month'),
    path('<slug:slug>/', views.PostDetailView.as_view(), name='post_detail'),
]
