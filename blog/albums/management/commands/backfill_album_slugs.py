from django.core.management.base import BaseCommand
from django.utils.text import slugify
from albums.models import Album

class Command(BaseCommand):
    help = 'Backfills slugs for albums based on their titles.'

    def handle(self, *args, **options):
        albums = Album.objects.filter(slug__isnull=True) | Album.objects.filter(slug='')
        count = 0
        for album in albums:
            base_slug = slugify(album.title) or 'album'
            slug = base_slug
            counter = 1
            while Album.objects.filter(slug=slug).exclude(id=album.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            album.slug = slug
            album.save()
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Successfully backfilled slugs for {count} albums.'))
