from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db.models import Count

from albums.cache_keys import (
    ALBUM_DETAIL_TTL,
    ALBUM_LIST_CACHE_KEY,
    ALBUM_LIST_TTL,
    get_album_detail_cache_key,
)
from albums.models import Album, PhotoStatus


class Command(BaseCommand):
    help = "Pre-populate album caches after deploy"

    def handle(self, *args, **kwargs):
        albums = list(
            Album.objects.annotate(photo_count=Count("photos"))
            .select_related("cover_photo")
            .order_by("-created_at")
        )
        cache.set(ALBUM_LIST_CACHE_KEY, albums, ALBUM_LIST_TTL)

        for album in albums:
            photos = list(album.photos.all())
            ready_photos = [photo for photo in photos if photo.status == PhotoStatus.READY and photo.image]
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
            cache.set(
                get_album_detail_cache_key(album.pk),
                {
                    "photos": photos,
                    "ready_photos": ready_photos,
                    "ready_photo_payloads": ready_photo_payloads,
                },
                ALBUM_DETAIL_TTL,
            )

        self.stdout.write(self.style.SUCCESS(f"Cache warmed: {len(albums)} albums"))
