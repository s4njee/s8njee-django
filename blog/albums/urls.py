from django.urls import path
from . import views

urlpatterns = [
    # URL names are the stable contract used by reverse() and template {% url %}.
    path("", views.AlbumListView.as_view(), name="album_list"),
    path("create/", views.album_create, name="album_create"),
    path("<uuid:pk>/edit/", views.album_edit, name="album_edit"),
    path("<uuid:pk>/delete/", views.album_delete, name="album_delete"),
    path("<uuid:pk>/", views.album_detail, name="album_detail"),
    path("s/<slug:slug>/", views.album_detail, name="album_detail_slug"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/set-cover/", views.album_set_cover_photo, name="album_set_cover_photo"),
    path("<uuid:album_pk>/upload/", views.photo_upload, name="photo_upload"),
    path("<uuid:album_pk>/upload/single/", views.photo_upload_single, name="photo_upload_single"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/edit/", views.photo_edit, name="photo_edit"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/delete/", views.photo_delete, name="photo_delete"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/move/<str:direction>/", views.photo_move, name="photo_move"),
    path("<uuid:album_pk>/photos/reorder/", views.photo_reorder, name="photo_reorder"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/status/", views.photo_status, name="photo_status"),
    path("<uuid:album_pk>/photos/<uuid:photo_pk>/", views.photo_permalink, name="photo_permalink"),
]
