from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from albums.models import Photo, PhotoStatus
from albums.tasks import process_photo


class Command(BaseCommand):
    help = "Reset photos stuck at PROCESSING and re-queue them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=int,
            default=10,
            metavar="MINUTES",
            help="Only retry photos that have been PROCESSING for at least this many minutes (default: 10).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be retried without making any changes.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options["older_than"])
        # uploaded_at is the best proxy for when processing started — a photo
        # stuck for more than N minutes was almost certainly orphaned by a
        # crashed or OOM-killed worker rather than still actively processing.
        stuck = Photo.objects.filter(
            status=PhotoStatus.PROCESSING,
            uploaded_at__lte=cutoff,
        )

        count = stuck.count()
        if count == 0:
            self.stdout.write("No stuck photos found.")
            return

        self.stdout.write(f"Found {count} photo(s) stuck at PROCESSING for >{options['older_than']}m.")

        if options["dry_run"]:
            for photo in stuck:
                self.stdout.write(f"  [dry-run] would retry {photo.pk} (album: {photo.album})")
            return

        retried = 0
        for photo in stuck:
            photo.status = PhotoStatus.PENDING
            photo.error = ""
            photo.save(update_fields=["status", "error"])
            process_photo.delay(str(photo.pk))
            self.stdout.write(f"  Queued {photo.pk} (album: {photo.album})")
            retried += 1

        self.stdout.write(self.style.SUCCESS(f"Re-queued {retried} photo(s)."))
