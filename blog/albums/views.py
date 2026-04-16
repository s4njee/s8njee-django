import json

from asgiref.sync import sync_to_async
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import aget_object_or_404, get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .forms import (
    AlbumDeleteForm,
    AlbumForm,
    PhotoDeleteForm,
    PhotoEditForm,
    PhotoUploadForm,
)
from .cache_keys import (
    ALBUM_DETAIL_TTL,
    ALBUM_LIST_CACHE_KEY,
    ALBUM_LIST_TTL,
    get_album_detail_cache_key,
)
from .models import Album, Photo, PhotoStatus
from .tasks import process_photo


class AlbumListView(ListView):
    # Generic ListView handles pagination-ready list rendering from a queryset.
    model = Album
    template_name = "albums/album_list.html"
    context_object_name = "albums"
    # ListView can render from a list, so this can return cached evaluated rows.
    def get_queryset(self):
        albums = cache.get(ALBUM_LIST_CACHE_KEY)
        if albums is None:
            albums = list(
                Album.objects.annotate(photo_count=Count("photos"))
                .select_related("cover_photo")
                .order_by("-created_at")
            )
            cache.set(ALBUM_LIST_CACHE_KEY, albums, ALBUM_LIST_TTL)
        return albums


def album_detail(request, pk=None, slug=None):
    if slug:
        # get_object_or_404 turns an empty queryset into Django's Http404 response.
        album = get_object_or_404(Album, slug=slug)
    else:
        album = get_object_or_404(Album, pk=pk)
    detail_cache_key = get_album_detail_cache_key(album.pk)
    detail_cache_payload = cache.get(detail_cache_key)
    if detail_cache_payload is None:
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
                "id": str(photo.pk),
                "url": photo.image.url,
                "url_medium": photo.image_medium.url if photo.image_medium else "",
                "url_small": photo.image_small.url if photo.image_small else "",
                "caption": photo.caption,
                "alt_text": photo.alt_text,
                "exif": photo.exif_display_items(),
            }
            for photo in ready_photos
        ]
        detail_cache_payload = {
            "photos": photos,
            "ready_photos": ready_photos,
            "ready_photo_payloads": ready_photo_payloads,
        }
        cache.set(detail_cache_key, detail_cache_payload, ALBUM_DETAIL_TTL)
    return render(
        # render combines the request, template, and context into an HttpResponse.
        request,
        "albums/album_detail.html",
        {
            "album": album,
            "photos": detail_cache_payload["photos"],
            "ready_photos": detail_cache_payload["ready_photos"],
            "ready_photo_payloads": detail_cache_payload["ready_photo_payloads"],
        },
    )


@staff_member_required
def album_create(request):
    # staff_member_required redirects non-staff users to the admin login.
    if request.method == "POST":
        form = AlbumForm(request.POST)
        if form.is_valid():
            album = form.save()
            return redirect("album_detail", pk=album.pk)
    else:
        form = AlbumForm()
    return render(
        request,
        "albums/album_form.html",
        {"form": form, "page_title": "New Album", "submit_label": "Create Album"},
    )


@staff_member_required
def album_edit(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if request.method == "POST":
        form = AlbumForm(request.POST, instance=album)
        if form.is_valid():
            saved_album = form.save()
            return redirect("album_detail", pk=saved_album.pk)
    else:
        form = AlbumForm(instance=album)
    return render(
        request,
        "albums/album_form.html",
        {
            "form": form,
            "album": album,
            "page_title": f"Edit {album.title}",
            "submit_label": "Save Album",
        },
    )


@staff_member_required
def album_delete(request, pk):
    album = get_object_or_404(Album, pk=pk)
    if request.method == "POST":
        form = AlbumDeleteForm(request.POST)
        if form.is_valid():
            for photo in album.photos.all():
                photo.delete_files()
            album.delete()
            return redirect("album_list")
    else:
        form = AlbumDeleteForm()
    return render(
        request,
        "albums/confirm_delete.html",
        {
            "object": album,
            "object_label": "album",
            "form": form,
            "back_url": reverse("album_detail", kwargs={"pk": album.pk}),
        },
    )


@staff_member_required
@require_POST
def album_set_cover_photo(request, album_pk, photo_pk):
    # require_POST rejects unsafe GET requests before the view mutates data.
    album = get_object_or_404(Album, pk=album_pk)
    photo = get_object_or_404(Photo, pk=photo_pk, album=album)
    if photo.status != PhotoStatus.READY or not photo.image:
        return JsonResponse({"error": "Choose a ready photo for the album cover."}, status=400)
    album.cover_photo = photo
    album.save(update_fields=["cover_photo", "updated_at"])
    return redirect("album_detail", pk=album.pk)


@staff_member_required
def photo_upload(request, album_pk):
    album = get_object_or_404(Album, pk=album_pk)
    return render(request, "albums/photo_upload.html", {"album": album})


def _photo_status_payload(photo: Photo, album_pk):
    # reverse keeps API payload links synced with urls.py names.
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


@staff_member_required
async def photo_upload_single(request, album_pk):
    """Accept a single photo upload and queue it for background processing.

    Async so uvicorn can handle concurrent uploads instead of serialising them
    behind a single thread-sensitive sync_to_async wrapper.
    """
    album = await aget_object_or_404(Album, pk=album_pk)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    # request.FILES carries uploaded file objects; request.POST only has form fields.
    form = PhotoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        errors = form.errors.get("image") or form.non_field_errors()
        return JsonResponse({"error": errors[0] if errors else "Invalid upload."}, status=400)

    photo = await Photo.objects.acreate(
        album=album,
        original=form.cleaned_data["image"],
        status=PhotoStatus.PENDING,
    )

    # Run on_commit + delay on the same executor thread that acreate used so
    # they share one DB connection (important for eager-mode Celery in tests).
    await sync_to_async(
        lambda: transaction.on_commit(lambda: process_photo.delay(str(photo.pk)))
    )()
    await photo.arefresh_from_db()

    status_code = 201 if photo.status == PhotoStatus.READY else 202
    return JsonResponse(_photo_status_payload(photo, album.pk), status=status_code)


@staff_member_required
def photo_edit(request, album_pk, photo_pk):
    album = get_object_or_404(Album, pk=album_pk)
    photo = get_object_or_404(Photo, pk=photo_pk, album=album)

    if request.method == "POST":
        # instance=photo tells ModelForm to update this row instead of creating one.
        form = PhotoEditForm(request.POST, request.FILES, instance=photo)
        if form.is_valid():
            replace_image = form.cleaned_data.get("replace_image")
            saved_photo = form.save(commit=False)
            if replace_image:
                old_files = [
                    (field_file.storage, field_file.name)
                    for field_file in [
                        saved_photo.image,
                        saved_photo.image_medium,
                        saved_photo.image_small,
                        saved_photo.thumbnail,
                        saved_photo.original,
                    ]
                    if field_file and field_file.name
                ]
                saved_photo.original = replace_image
                saved_photo.image = ""
                saved_photo.image_medium = ""
                saved_photo.image_small = ""
                saved_photo.thumbnail = ""
                saved_photo.exif_data = {}
                saved_photo.error = ""
                saved_photo.status = PhotoStatus.PENDING
                saved_photo.save()
                for storage, name in old_files:
                    storage.delete(name)
                transaction.on_commit(lambda: process_photo.delay(str(saved_photo.pk)))
            else:
                saved_photo.save()
            return redirect("album_detail", pk=album.pk)
    else:
        form = PhotoEditForm(instance=photo)

    return render(
        request,
        "albums/photo_form.html",
        {
            "album": album,
            "photo": photo,
            "form": form,
            "page_title": "Edit Photo",
            "submit_label": "Save Photo",
        },
    )


@staff_member_required
def photo_delete(request, album_pk, photo_pk):
    album = get_object_or_404(Album, pk=album_pk)
    photo = get_object_or_404(Photo, pk=photo_pk, album=album)
    if request.method == "POST":
        form = PhotoDeleteForm(request.POST)
        if form.is_valid():
            photo.delete_files()
            photo.delete()
            return redirect("album_detail", pk=album.pk)
    else:
        form = PhotoDeleteForm()
    return render(
        request,
        "albums/confirm_delete.html",
        {
            "object": photo,
            "object_label": "photo",
            "form": form,
            "back_url": reverse("album_detail", kwargs={"pk": album.pk}),
        },
    )


@staff_member_required
@require_POST
def photo_move(request, album_pk, photo_pk, direction):
    album = get_object_or_404(Album, pk=album_pk)
    photo = get_object_or_404(Photo, pk=photo_pk, album=album)
    if direction not in {"up", "down"}:
        return JsonResponse({"error": "Invalid direction."}, status=400)

    # select_for_update locks rows during this reorder transaction.
    with transaction.atomic():
        photo = Photo.objects.select_for_update().get(pk=photo.pk, album=album)
        if direction == "up":
            neighbor = (
                Photo.objects.select_for_update()
                .filter(album=album, sort_order__lt=photo.sort_order)
                .order_by("-sort_order", "-uploaded_at")
                .first()
            )
        else:
            neighbor = (
                Photo.objects.select_for_update()
                .filter(album=album, sort_order__gt=photo.sort_order)
                .order_by("sort_order", "uploaded_at")
                .first()
            )

        if neighbor:
            photo.sort_order, neighbor.sort_order = neighbor.sort_order, photo.sort_order
            photo.save(update_fields=["sort_order"])
            neighbor.save(update_fields=["sort_order"])

    return redirect("album_detail", pk=album.pk)


@staff_member_required
@require_POST
def photo_reorder(request, album_pk):
    album = get_object_or_404(Album, pk=album_pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    ordered_photo_ids = payload.get("ordered_photo_ids")
    if not isinstance(ordered_photo_ids, list):
        return JsonResponse({"error": "ordered_photo_ids must be a list."}, status=400)

    existing_ids = list(Photo.objects.filter(album=album).values_list("id", flat=True))
    existing_id_set = {str(photo_id) for photo_id in existing_ids}
    ordered_id_set = {str(photo_id) for photo_id in ordered_photo_ids}
    if len(ordered_photo_ids) != len(existing_ids) or ordered_id_set != existing_id_set:
        return JsonResponse({"error": "Photo order does not match this album."}, status=400)

    # Atomic bulk reordering avoids partially-saved drag-and-drop order.
    with transaction.atomic():
        locked_photos = {
            str(photo.pk): photo
            for photo in Photo.objects.select_for_update().filter(album=album)
        }
        for sort_order, photo_id in enumerate(ordered_photo_ids):
            photo = locked_photos[str(photo_id)]
            if photo.sort_order != sort_order:
                photo.sort_order = sort_order
                photo.save(update_fields=["sort_order"])

    return JsonResponse({"ok": True})


@staff_member_required
async def photo_status(request, album_pk, photo_pk):
    album = await aget_object_or_404(Album, pk=album_pk)
    photo = await aget_object_or_404(Photo, pk=photo_pk, album=album)
    return JsonResponse(_photo_status_payload(photo, album.pk))


def photo_permalink(request, album_pk, photo_pk):
    """Redirect to the album detail page with the lightbox pre-opened for the given photo."""
    album = get_object_or_404(Album, pk=album_pk)
    get_object_or_404(Photo, pk=photo_pk, album=album)
    url = reverse("album_detail", kwargs={"pk": album_pk})
    # HttpResponseRedirect is useful when the redirect target includes a hash fragment.
    return HttpResponseRedirect(f"{url}#photo-{photo_pk}")
