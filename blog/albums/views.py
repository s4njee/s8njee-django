from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView
from django.core.files.base import ContentFile
import io
import os
import rawpy
from PIL import Image
import pillow_heif

from .models import Album, Photo
from .forms import AlbumForm

pillow_heif.register_avif_opener()


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
    """Accept a single photo upload via XHR, processing raw files."""
    album = get_object_or_404(Album, pk=album_pk)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    
    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image provided"}, status=400)
    
    # Process Nikon RAW files (or other RAW formats like cr2/dng)
    if image.name.lower().endswith(('.nef', '.cr2', '.dng', '.arw')):
        file_bytes = image.read()
        image.seek(0)
        
        # 1. Try to extract original EXIF from the RAW
        # Since many RAW formats (like inside NEF) are based on the TIFF spec, 
        # PIL can sometimes read the EXIF header before failing to read actual pixel data.
        exif_bytes = b""
        try:
            temp_img = Image.open(image)
            if "exif" in temp_img.info:
                exif_bytes = temp_img.info["exif"]
        except Exception:
            pass
        
        # 2. Extract pixel data with rawpy
        try:
            with rawpy.imread(io.BytesIO(file_bytes)) as raw:
                # postprocess handles demosaicing, white balance, etc.
                rgb = raw.postprocess()
                
            img = Image.fromarray(rgb)
            
            # 3. Save as AVIF, injecting the EXIF back in
            out_buf = io.BytesIO()
            save_kwargs = {"format": "AVIF", "quality": 85}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
                
            img.save(out_buf, **save_kwargs)
            out_buf.seek(0)
            
            # Replace the in-memory uploaded image with our new AVIF ContentFile
            new_filename = os.path.splitext(image.name)[0] + ".avif"
            image = ContentFile(out_buf.read(), name=new_filename)
        except Exception as e:
            return JsonResponse({"error": f"Failed to process RAW file: {str(e)}"}, status=400)

    photo = Photo.objects.create(album=album, image=image)
    return JsonResponse({"id": str(photo.pk), "url": photo.image.url}, status=201)

