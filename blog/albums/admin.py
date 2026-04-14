from django.contrib import admin
from .models import Album, Photo


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    fields = ["sort_order", "caption", "status", "image", "thumbnail"]
    ordering = ["sort_order", "-uploaded_at"]


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ["title", "created_at"]
    inlines = [PhotoInline]


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "album", "sort_order", "status", "uploaded_at"]
    ordering = ["album", "sort_order", "-uploaded_at"]
    list_filter = ["status", "uploaded_at"]
    search_fields = ["caption", "album__title", "error"]
