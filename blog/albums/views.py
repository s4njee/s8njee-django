import os

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView

from PIL import Image, UnidentifiedImageError

from .image_processing import RAW_EXTENSIONS
from .forms import AlbumForm
from .models import Album, Photo, PhotoStatus
from .tasks import process_photo


class AlbumListView(ListView):
    model = Album
    template_name = "albums/album_list.html"
    context_object_name = "albums"


def album_detail(request, pk):
    album = get_object_or_404(Album, pk=pk)
    photos = list(album.photos.all())
    ready_photos = [photo for photo in photos if photo.status == PhotoStatus.READY and photo.image]
    ready_index = 0
    for photo in photos:
        if photo.status == PhotoStatus.READY and photo.image:
            photo.ready_index = ready_index
            ready_index += 1
        else:
            photo.ready_index = None
    ready_photo_payloads = [
        {
            "url": photo.image.url,
            "caption": photo.caption,
            "exif": photo.exif_display_items(),
        }
        for photo in ready_photos
    ]
    return render(
        request,
        "albums/album_detail.html",
        {
            "album": album,
            "photos": photos,
            "ready_photos": ready_photos,
            "ready_photo_payloads": ready_photo_payloads,
        },
    )


@login_required
def album_create(request):
    if request.method == "POST":
        form = AlbumForm(request.POST)
        if form.is_valid():
            album = form.save()
            return redirect("album_detail", pk=album.pk)
    else:
        form = AlbumForm()
    return render(request, "albums/album_form.html", {"form": form})


@login_required
def photo_upload(request, album_pk):
    album = get_object_or_404(Album, pk=album_pk)
    return render(request, "albums/photo_upload.html", {"album": album})


def _photo_status_payload(photo: Photo, album_pk):
    payload = {
        "id": str(photo.pk),
        "album_id": str(album_pk),
        "status": photo.status,
        "poll_url": reverse("photo_status", kwargs={"album_pk": album_pk, "photo_pk": photo.pk}),
    }
    if photo.status == PhotoStatus.READY:
        payload["url"] = photo.image.url
        if photo.thumbnail:
            payload["thumbnail_url"] = photo.thumbnail.url
    if photo.status == PhotoStatus.FAILED and photo.error:
        payload["error"] = photo.error
    return payload


@login_required
def photo_upload_single(request, album_pk):
    """Accept a single photo upload and queue it for background processing."""
    album = get_object_or_404(Album, pk=album_pk)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image provided"}, status=400)

    ext = os.path.splitext(image.name)[1].lower()

    if ext not in RAW_EXTENSIONS:
        try:
            opened = Image.open(image)
            opened.verify()
            image.seek(0)
        except (UnidentifiedImageError, OSError):
            return JsonResponse({"error": "The uploaded file is not a supported image."}, status=400)

    photo = Photo.objects.create(
        album=album,
        original=image,
        status=PhotoStatus.PENDING,
    )

    def queue_photo_processing() -> None:
        process_photo.delay(str(photo.pk))

    transaction.on_commit(queue_photo_processing)
    photo.refresh_from_db()

    status_code = 201 if photo.status == PhotoStatus.READY else 202
    return JsonResponse(_photo_status_payload(photo, album.pk), status=status_code)


@login_required
def photo_status(request, album_pk, photo_pk):
    album = get_object_or_404(Album, pk=album_pk)
    photo = get_object_or_404(Photo, pk=photo_pk, album=album)
    return JsonResponse(_photo_status_payload(photo, album.pk))
