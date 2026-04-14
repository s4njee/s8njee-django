from django.core.management.base import BaseCommand
from django.db.models import Max, Min

from albums.models import Album, Photo


class Command(BaseCommand):
    # Django discovers this as manage.py backfill_photo_sort_order from its filename.
    help = "Backfill sequential photo sort order for albums that still have default ordering"

    def handle(self, *args, **options):
        albums_updated = 0
        photos_updated = 0

        for album in Album.objects.all():
            qs = Photo.objects.filter(album=album)
            total = qs.count()
            if total <= 1:
                continue
            stats = qs.aggregate(min_sort_order=Min("sort_order"), max_sort_order=Max("sort_order"))
            if stats["min_sort_order"] != 0 or stats["max_sort_order"] != 0:
                continue

            for sort_order, photo in enumerate(qs.order_by("-uploaded_at", "-id")):
                Photo.objects.filter(pk=photo.pk).update(sort_order=sort_order)
                photos_updated += 1
            albums_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfilled sort order for {albums_updated} album(s) and {photos_updated} photo(s)."
            )
        )
