from django.core.management.base import BaseCommand
from albums.models import Photo


class Command(BaseCommand):
    # BaseCommand.handle() is the entrypoint for custom manage.py commands.
    help = "Generate thumbnails for existing photos that don't have one"

    def handle(self, *args, **options):
        photos = Photo.objects.filter(thumbnail="")
        total = photos.count()
        self.stdout.write(f"Found {total} photos without thumbnails")

        for i, photo in enumerate(photos.iterator(), 1):
            try:
                photo._make_thumbnail()
                photo.save(update_fields=["thumbnail"])
                self.stdout.write(f"  [{i}/{total}] ✓ {photo.id}")
            except Exception as e:
                self.stderr.write(f"  [{i}/{total}] ✗ {photo.id}: {e}")

        self.stdout.write(self.style.SUCCESS("Done!"))
