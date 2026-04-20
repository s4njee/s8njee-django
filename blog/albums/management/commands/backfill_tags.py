"""
Management command to auto-tag existing photos that don't have tags yet.

Usage:
    python manage.py backfill_tags          # Queue all untagged photos
    python manage.py backfill_tags --sync   # Run synchronously (no Celery)
    python manage.py backfill_tags --limit=50
"""
from django.core.management.base import BaseCommand

from albums.models import Photo, PhotoStatus


class Command(BaseCommand):
    help = "Auto-tag photos that have no tags using the LLM vision model."

    def add_arguments(self, parser):
        parser.add_argument("--sync", action="store_true", help="Run synchronously instead of queuing Celery tasks.")
        parser.add_argument("--limit", type=int, default=0, help="Max photos to process (0 = all).")

    def handle(self, *args, **options):
        from django.conf import settings

        if not settings.AUTO_TAG_ENABLED:
            self.stderr.write(self.style.WARNING("AUTO_TAG_ENABLED is False. Set it to True and provide AUTO_TAG_API_KEY."))
            return

        qs = Photo.objects.filter(status=PhotoStatus.READY, tags__isnull=True).distinct()
        if options["limit"]:
            qs = qs[:options["limit"]]

        photos = list(qs)
        self.stdout.write(f"Found {len(photos)} untagged photo(s).")

        if options["sync"]:
            from albums.tagging import apply_tags_to_photo, generate_tags_for_image

            for photo in photos:
                image_field = photo.image_small or photo.image_medium or photo.image
                if not image_field:
                    continue
                with image_field.open("rb") as fh:
                    image_bytes = fh.read()
                name = (image_field.name or "").lower()
                if name.endswith(".png"):
                    ct = "image/png"
                elif name.endswith(".webp"):
                    ct = "image/webp"
                elif name.endswith(".avif"):
                    ct = "image/avif"
                else:
                    ct = "image/jpeg"
                tag_names = generate_tags_for_image(image_bytes, ct)
                if tag_names:
                    apply_tags_to_photo(photo, tag_names)
                    self.stdout.write(f"  {photo.pk}: {tag_names}")
                else:
                    self.stdout.write(f"  {photo.pk}: no tags returned")
        else:
            from albums.tasks import auto_tag_photo

            for photo in photos:
                auto_tag_photo.delay(str(photo.pk))
            self.stdout.write(f"Queued {len(photos)} auto-tag task(s).")
