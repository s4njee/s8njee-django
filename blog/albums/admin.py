from django.contrib import admin
from django.utils import timezone
from datetime import timedelta

from .models import Album, Photo, PhotoStatus
from .tasks import process_photo


class PhotoInline(admin.TabularInline):
    # TabularInline edits related Photo rows on the Album admin page.
    model = Photo
    extra = 0
    fields = ["sort_order", "caption", "status", "image", "thumbnail"]
    ordering = ["sort_order", "-uploaded_at"]


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    # Registering ModelAdmin classes wires models into /admin/.
    list_display = ["title", "created_at"]
    inlines = [PhotoInline]


def retry_stuck_photos(modeladmin, request, queryset):
    # Re-queue selected PROCESSING photos; also picks up any globally stuck
    # ones older than 10 minutes regardless of the checkbox selection.
    stuck = queryset.filter(status=PhotoStatus.PROCESSING)
    count = 0
    for photo in stuck:
        photo.status = PhotoStatus.PENDING
        photo.error = ""
        photo.save(update_fields=["status", "error"])
        process_photo.delay(str(photo.pk))
        count += 1
    modeladmin.message_user(request, f"Re-queued {count} photo(s).")

retry_stuck_photos.short_description = "Retry selected stuck/processing photos"


def retry_all_stuck_photos(modeladmin, request, queryset):
    # Ignores the queryset selection — retries every PROCESSING photo older
    # than 10 minutes site-wide. Useful when you just want to clear the backlog.
    cutoff = timezone.now() - timedelta(minutes=10)
    stuck = Photo.objects.filter(status=PhotoStatus.PROCESSING, uploaded_at__lte=cutoff)
    count = 0
    for photo in stuck:
        photo.status = PhotoStatus.PENDING
        photo.error = ""
        photo.save(update_fields=["status", "error"])
        process_photo.delay(str(photo.pk))
        count += 1
    modeladmin.message_user(request, f"Re-queued {count} stuck photo(s) (all albums).")

retry_all_stuck_photos.short_description = "Retry ALL stuck photos (site-wide, >10 min)"


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    # Admin list/search options operate through Django ORM fields and lookups.
    list_display = ["__str__", "album", "sort_order", "status", "uploaded_at"]
    ordering = ["album", "sort_order", "-uploaded_at"]
    list_filter = ["status", "uploaded_at"]
    search_fields = ["caption", "album__title", "error"]
    actions = [retry_stuck_photos, retry_all_stuck_photos]
