import io
import uuid

from django.core.files.base import ContentFile
from django.db import models
from PIL import Image
import pillow_heif

# Register HEIF/AVIF support in Pillow (handles both .heic and .avif)
pillow_heif.register_heif_opener()

THUMBNAIL_MAX_WIDTH = 400


class Album(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="photos/%Y/%m/%d/")
    thumbnail = models.ImageField(upload_to="photos/%Y/%m/%d/thumbs/", blank=True)
    caption = models.CharField(max_length=300, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.caption or f"Photo in {self.album.title}"

    def save(self, *args, **kwargs):
        # Generate thumbnail from image before saving
        if self.image and not self.thumbnail:
            self._make_thumbnail()
        super().save(*args, **kwargs)

    def _make_thumbnail(self):
        img = Image.open(self.image)
        img.thumbnail((THUMBNAIL_MAX_WIDTH, THUMBNAIL_MAX_WIDTH * 2), Image.LANCZOS)

        # Determine output format based on stored file extension
        name = self.image.name.lower()
        if name.endswith(".png"):
            fmt, ext = "PNG", ".png"
        elif name.endswith(".webp"):
            fmt, ext = "WEBP", ".webp"
        elif name.endswith(".avif"):
            fmt, ext = "AVIF", ".avif"
        else:
            fmt, ext = "JPEG", ".jpg"

        buf = io.BytesIO()
        save_kwargs = {"format": fmt}
        if fmt == "JPEG":
            save_kwargs["quality"] = 80
        img.save(buf, **save_kwargs)
        buf.seek(0)

        thumb_name = f"thumb_{self.id}{ext}"
        self.thumbnail.save(thumb_name, ContentFile(buf.read()), save=False)
