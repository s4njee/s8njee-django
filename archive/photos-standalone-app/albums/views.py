from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from .models import Album, Photo
from .forms import AlbumForm


class AlbumListView(ListView):
    model = Album
    template_name = "albums/album_list.html"
    context_object_name = "albums"


def album_detail(request, pk):
    album = get_object_or_404(Album, pk=pk)
    return render(request, "albums/album_detail.html", {"album": album})


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


@login_required
def photo_upload_single(request, album_pk):
    """Accept a single photo upload via XHR."""
    album = get_object_or_404(Album, pk=album_pk)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image provided"}, status=400)
    photo = Photo.objects.create(album=album, image=image)
    return JsonResponse({"id": str(photo.pk), "url": photo.image.url}, status=201)
