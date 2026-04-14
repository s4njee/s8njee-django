import uuid

from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Max

from .image_processing import extract_exif_summary, make_thumbnail_from_image_file


class PhotoStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class Album(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    cover_photo = models.ForeignKey(
        "Photo",
        on_delete=models.SET_NULL,
        related_name="cover_for_albums",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def cover_photo_for_display(self):
        cover = self.cover_photo
        if cover and cover.status == PhotoStatus.READY and cover.image:
            return cover

        for photo in self.photos.all():
            if photo.status == PhotoStatus.READY and photo.image:
                return photo
        return None


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="photos")
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    image = models.ImageField(upload_to="photos/%Y/%m/%d/", blank=True)
    image_medium = models.ImageField(upload_to="photos/%Y/%m/%d/", blank=True)
    image_small = models.ImageField(upload_to="photos/%Y/%m/%d/", blank=True)
    thumbnail = models.ImageField(upload_to="photos/%Y/%m/%d/thumbs/", blank=True)
    original = models.FileField(upload_to="photos/originals/%Y/%m/%d/", blank=True)
    exif_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=PhotoStatus.choices,
        default=PhotoStatus.PENDING,
        db_index=True,
    )
    error = models.TextField(blank=True)
    caption = models.CharField(max_length=300, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "-uploaded_at"]

    def __str__(self):
        return self.caption or f"Photo in {self.album.title}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.sort_order == 0:
            next_order = (
                Photo.objects.filter(album=self.album)
                .aggregate(max_sort_order=Max("sort_order"))
                .get("max_sort_order")
            )
            self.sort_order = 0 if next_order is None else next_order + 1
        super().save(*args, **kwargs)

    def _make_thumbnail(self):
        if not self.image:
            raise ValueError("Cannot build a thumbnail without an image.")
        thumb_name, thumb_bytes = make_thumbnail_from_image_file(self.image, str(self.id))
        self.thumbnail.save(thumb_name, ContentFile(thumb_bytes), save=False)

    def delete_files(self):
        for field_name in ("image", "image_medium", "image_small", "thumbnail", "original"):
            field_file = getattr(self, field_name)
            if field_file and field_file.name:
                field_file.storage.delete(field_file.name)

    def exif_display_items(self):
        data = self.exif_data or {}
        if not data:
            source_file = self.original or self.image
            if source_file:
                try:
                    source_file.open("rb")
                    try:
                        data = extract_exif_summary(source_file.read())
                    finally:
                        source_file.close()
                except Exception:
                    data = {}
        return [{"label": label, "value": value} for label, value in data.items()]
