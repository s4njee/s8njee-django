from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import UnidentifiedImageError

from albums.image_processing import make_image_variant
from albums.models import Photo, PhotoStatus

VARIANTS = [
    (1200, "1200", "image_medium"),
    (800, "800", "image_small"),
]


class Command(BaseCommand):
    # BaseCommand gives us styled stdout/stderr and option parsing.
    help = "Generate missing image_medium and image_small variants for existing ready photos."

    def handle(self, *args, **options):
        qs = Photo.objects.filter(status=PhotoStatus.READY).exclude(image="")
        total = qs.count()
        self.stdout.write(f"Checking {total} ready photos…")

        generated = skipped = failed = 0
        for i, photo in enumerate(qs.iterator(), 1):
            missing = [(d, s, a) for d, s, a in VARIANTS if not getattr(photo, a)]
            if not missing:
                skipped += 1
                continue

            try:
                with photo.image.open("rb") as fh:
                    full_bytes = fh.read()
                full_name = photo.image.name

                changed_fields = []
                for max_dim, suffix, attr in missing:
                    variant_name, variant_bytes = make_image_variant(
                        full_bytes, full_name, max_dim, str(photo.id), suffix
                    )
                    getattr(photo, attr).save(variant_name, ContentFile(variant_bytes), save=False)
                    changed_fields.append(attr)

                photo.save(update_fields=changed_fields)
                generated += 1
                self.stdout.write(f"  [{i}/{total}] {photo.id}: generated {', '.join(changed_fields)}")
            except (OSError, UnidentifiedImageError) as exc:
                # Narrow catch: storage misses and unreadable image data are
                # legitimate "skip and keep going" cases for a backfill script.
                # Unexpected exceptions should crash the command so bugs surface.
                failed += 1
                self.stderr.write(f"  [{i}/{total}] {photo.id}: FAILED — {exc}")

        self.stdout.write(
            f"\nDone. Generated: {generated}  Skipped (already had variants): {skipped}  Failed: {failed}"
        )
