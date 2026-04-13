from django.contrib import admin
from .models import Album, Photo


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 1


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ["title", "created_at"]
    inlines = [PhotoInline]


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "album", "status", "uploaded_at"]
    list_filter = ["status", "uploaded_at"]
    search_fields = ["caption", "album__title", "error"]
