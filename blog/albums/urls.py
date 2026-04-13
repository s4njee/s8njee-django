from django.urls import path
from . import views

urlpatterns = [
    path("", views.AlbumListView.as_view(), name="album_list"),
    path("create/", views.album_create, name="album_create"),
    path("<uuid:pk>/", views.album_detail, name="album_detail"),
    path("<uuid:album_pk>/upload/", views.photo_upload, name="photo_upload"),
    path("<uuid:album_pk>/upload/single/", views.photo_upload_single, name="photo_upload_single"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/status/", views.photo_status, name="photo_status"),
]
