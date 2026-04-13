import io
import os

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from PIL import Image
import pillow_heif
import rawpy

from .models import Album, Photo
from .forms import AlbumForm

# Register HEIF/AVIF support in Pillow at module load time
pillow_heif.register_heif_opener()

RAW_EXTENSIONS = {'.nef', '.cr2', '.cr3', '.dng', '.arw', '.orf', '.raf', '.rw2'}

# Cap the longest edge at this size (1920 = standard 1080p width)
MAX_DIMENSION = 1920


def _downscale_if_needed(img: Image.Image) -> Image.Image:
    """Return a resized copy if either dimension exceeds MAX_DIMENSION."""
    w, h = img.size
    if w <= MAX_DIMENSION and h <= MAX_DIMENSION:
        return img
    scale = MAX_DIMENSION / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


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
    """Accept a single photo upload via XHR, converting RAW files to AVIF."""
    album = get_object_or_404(Album, pk=album_pk)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image provided"}, status=400)

    ext = os.path.splitext(image.name)[1].lower()

    if ext in RAW_EXTENSIONS:
        file_bytes = image.read()

        # 1. Try to rescue original EXIF from the RAW's TIFF-based header
        exif_bytes = b""
        try:
            image.seek(0)
            temp_img = Image.open(image)
            if "exif" in temp_img.info:
                exif_bytes = temp_img.info["exif"]
        except Exception:
            pass

        # 2. Demosaic raw pixel data with rawpy
        try:
            with rawpy.imread(io.BytesIO(file_bytes)) as raw:
                rgb = raw.postprocess()

            img = Image.fromarray(rgb)
            img = _downscale_if_needed(img)

            # 3. Encode as AVIF, injecting rescued EXIF
            out_buf = io.BytesIO()
            save_kwargs = {"format": "AVIF", "quality": 85}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            img.save(out_buf, **save_kwargs)
            out_buf.seek(0)

            new_filename = os.path.splitext(image.name)[0] + ".avif"
            image = ContentFile(out_buf.read(), name=new_filename)

        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to process RAW file: {e}"}, status=400
            )

    # Downscale regular (non-RAW) images exceeding 1080p
    else:
        try:
            orig = Image.open(image)
            resized = _downscale_if_needed(orig)
            if resized is not orig:  # only rewrite if we actually scaled
                out_buf = io.BytesIO()
                fmt = orig.format or "JPEG"
                save_kwargs = {"format": fmt}
                if fmt == "JPEG":
                    save_kwargs["quality"] = 85
                resized.save(out_buf, **save_kwargs)
                out_buf.seek(0)
                image = ContentFile(out_buf.read(), name=image.name)
        except Exception:
            pass  # If anything goes wrong, upload the original untouched

    photo = Photo.objects.create(album=album, image=image)
    return JsonResponse({"id": str(photo.pk), "url": photo.image.url}, status=201)
