# Caching Implementation Guide

## Overview

The site is read-heavy with a single writer. Caching is most valuable on the album list and album detail pages, which hit multiple tables and generate per-album photo counts. Blog post pages are cheaper and lower priority.

Redis (Valkey) is already running for Celery, so no new infrastructure is needed — just a second DB index.

---

## 1. Add the cache backend

`REDIS_URL` is a separate env var from `CELERY_BROKER_URL`. Add to `blog/blog/settings/base.py`:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        # DB index 1 keeps cache separate from Celery's queue (DB 0).
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
    }
}
```

Add `REDIS_URL` to `blog/.env.example`:

```
REDIS_URL=redis://localhost:6379/1
```

In the Kubernetes ConfigMaps, set `REDIS_URL` to the same Valkey host as `CELERY_BROKER_URL` but on DB index 1:

```
REDIS_URL=redis://valkey:6379/1
```

`REDIS_URL` can stay in ConfigMap (same value as `CELERY_BROKER_URL` with `/1` instead of `/0`) since it is not sensitive.

In `settings/development.py`, override to use the dummy backend so local dev doesn't require Redis:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}
```

---

## 2. Fix the N+1 on album list first

Before adding cache, fix the existing N+1 query (tracked in ToDo bugs). This is free and reduces load regardless of caching:

```python
# albums/views.py — AlbumListView
from django.db.models import Count

class AlbumListView(ListView):
    def get_queryset(self):
        return (
            Album.objects.annotate(photo_count=Count("photos"))
            .select_related("cover_photo")
            .order_by("-created_at")
        )
```

Update the template to use `album.photo_count` instead of `album.photos.count`.

---

## 3. Cache the album list query

After fixing the N+1, wrap the queryset in a low-level cache call:

```python
from django.core.cache import cache

ALBUM_LIST_CACHE_KEY = "album_list"
ALBUM_LIST_TTL = 300  # 5 minutes — also invalidated immediately on any write (see step 4)

class AlbumListView(ListView):
    def get_queryset(self):
        qs = cache.get(ALBUM_LIST_CACHE_KEY)
        if qs is None:
            qs = list(
                Album.objects.annotate(photo_count=Count("photos"))
                .select_related("cover_photo")
                .order_by("-created_at")
            )
            cache.set(ALBUM_LIST_CACHE_KEY, qs, ALBUM_LIST_TTL)
        return qs
```

`list()` forces evaluation before storing — Django querysets are lazy and can't be pickled reliably.

---

## 4. Signal-based invalidation

Cache is invalidated immediately on any write — no waiting for TTL expiry. Add signals to `albums/models.py`:

```python
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

@receiver([post_save, post_delete], sender=Album)
@receiver([post_save, post_delete], sender=Photo)
def invalidate_album_cache(sender, **kwargs):
    cache.delete(ALBUM_LIST_CACHE_KEY)
```

Move cache key constants to a shared module (`albums/cache_keys.py`) to avoid circular imports between models and views.

This covers all write paths: creating, editing, or deleting an album or photo immediately busts the relevant cache entry. The TTL (5 min) is a safety net for anything that slips through.

Blog posts are not cached — they are plain text with a single DB row per page, so the query cost is negligible.

---

## 5. Album detail caching

Album detail pages load all photos for an album. Since albums are created infrequently and upload sessions are self-healing (the page reflects reality once processing completes), a simple per-album cache with signal invalidation is sufficient:

```python
def get_album_detail_cache_key(album_pk):
    return f"album_detail_{album_pk}"

ALBUM_DETAIL_TTL = 300

# In album_detail view:
cache_key = get_album_detail_cache_key(album.pk)
payload = cache.get(cache_key)
if payload is None:
    photos = list(album.photos.all())  # all statuses — template shows processing indicators
    ready_photos = [p for p in photos if p.status == PhotoStatus.READY and p.image]
    ready_photo_payloads = [
        {"id": str(p.pk), "url": p.image.url, "caption": p.caption, ...}
        for p in ready_photos
    ]
    payload = {"photos": photos, "ready_photos": ready_photos, "ready_photo_payloads": ready_photo_payloads}
    cache.set(cache_key, payload, ALBUM_DETAIL_TTL)
```

The `invalidate_album_cache` signal (step 4) should also delete the per-album key:

```python
@receiver([post_save, post_delete], sender=Photo)
def invalidate_album_cache(sender, instance, **kwargs):
    cache.delete(ALBUM_LIST_CACHE_KEY)
    cache.delete(get_album_detail_cache_key(instance.album_id))
```

During an active upload session, photos with `status="processing"` are excluded from the cached queryset anyway, so stale cache only means a short delay before a newly-ready photo appears — acceptable given the 5-minute TTL and signal invalidation on `Photo.post_save`.

---

## 6. Template fragment caching for album cards (optional)

If the album list is still slow after steps 2–5, cache the rendered HTML per card. The `album.updated_at` timestamp in the key auto-invalidates the fragment when the album is edited:

```django
{% load cache %}

{% for album in object_list %}
  {% cache 300 album_card album.pk album.updated_at %}
    {# existing album card HTML #}
  {% endcache %}
{% endfor %}
```

---

## 7. Cache warming on deploy

Add a management command `warm_cache` that pre-populates the album list and post list caches. Call it from `start.sh` after `collectstatic`:

```python
# albums/management/commands/warm_cache.py
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.db.models import Count
from albums.models import Album
from albums.cache_keys import ALBUM_LIST_CACHE_KEY, ALBUM_LIST_TTL, get_album_detail_cache_key, ALBUM_DETAIL_TTL

class Command(BaseCommand):
    help = "Pre-populate Redis cache after deploy"

    def handle(self, *args, **kwargs):
        albums = list(
            Album.objects.annotate(photo_count=Count("photos"))
            .select_related("cover_photo")
            .order_by("-created_at")
        )
        cache.set(ALBUM_LIST_CACHE_KEY, albums, ALBUM_LIST_TTL)

        for album in albums:
            photos = list(album.photos.filter(status="ready").order_by("sort_order"))
            cache.set(get_album_detail_cache_key(album.pk), photos, ALBUM_DETAIL_TTL)

        self.stdout.write(self.style.SUCCESS(f"Cache warmed: {len(albums)} albums"))
```

Add to `blog/start.sh` after `collectstatic`:

```sh
uv run python manage.py warm_cache
```

---

## 8. What not to cache

- **Staff views** (edit/delete/upload forms) — low traffic, not worth the complexity
- **Individual post detail** — one DB row, Markdown render is fast
- **Photo upload/processing** — already async via Celery
- **Per-view or site-wide caching** — avoid; staff UI is mixed into the same views

---

## Verification

Install Django Debug Toolbar to confirm query counts before and after:

```bash
uv add --dev django-debug-toolbar
```

```python
# settings/development.py
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
INTERNAL_IPS = ["127.0.0.1"]
```

```python
# blog/urls.py (dev only)
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
```

The toolbar's SQL panel shows exactly how many queries each page fires and which are duplicates.
