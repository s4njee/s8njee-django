# Django Photoblog Expansion Ideas

This document outlines potential features and technical deep-dives to expand your site while giving you hands-on experience with the broader Django ecosystem.

---

## Next Wave (Unfinished — Top of Queue)

Fresh ideas weighted toward Django ecosystem depth and the photoblog's specific shape.

### 1. Photo Map with GeoDjango + PostGIS
*   **What:** A world map of where photos were taken, built from EXIF GPS data that's already being extracted.
*   **Django Ecosystem:** `django.contrib.gis`, `PointField`, spatial querysets (`distance_lt`, bounding-box filters), PostGIS extension. Leaflet frontend fed by a lightweight GeoJSON endpoint from a Django view.

### 2. `django-filter` Archive Browsing by EXIF
*   **What:** A filterable archive: camera body, lens, year, ISO bucket, shutter-speed range.
*   **Django Ecosystem:** `FilterSet`, URL-driven querysets, composable filters. Natural fit for EXIF-rich data and arguably more useful than tagging for a bespoke site.

### 3. Scheduled Publishing with `django-celery-beat`
*   **What:** Draft posts with a `publish_at` timestamp; a beat schedule moves them to published automatically.
*   **Django Ecosystem:** Uses the existing Celery/Valkey setup. Teaches periodic tasks, the DB-backed scheduler, and the distinction between one-shot and recurring work.

### 4. Content Versioning with `django-reversion`
*   **What:** Full revision history on posts/albums, surfaced in the admin with revert workflows.
*   **Django Ecosystem:** Signal-driven change tracking and how third-party apps hook into `ModelAdmin`. Editorial safety net.

### 5. Signed Preview Links for Drafts
*   **What:** Share a draft via a tokenized, expiring URL.
*   **Django Ecosystem:** `django.core.signing.TimestampSigner`, custom view with token verification. Small surface, exposes Django's cryptographic signing primitives without needing third-party auth.

### 6. Management-Command Layer for Photo Workflows
*   **What:** `regenerate_variants`, `prune_orphaned_media`, `import_from_folder`, `exif_report`.
*   **Django Ecosystem:** `BaseCommand`, argparse integration, `transaction.atomic`. Gives real ops tooling for the netcup deployment.

### 7. Custom Model Field: `ExifShutterField` / `ApertureField`
*   **What:** Round-trip `"1/250"` ↔ float, or `f/2.8` ↔ decimal, with proper form-field coercion.
*   **Django Ecosystem:** `to_python`, `get_prep_value`, `from_db_value`, form-field overrides. A rare corner of the ORM most Django devs never touch.

### 8. Dynamic OpenGraph Cards via Pillow
*   **What:** Per-post social-share image composited from the hero photo + title overlay, cached and served from a signed URL.
*   **Django Ecosystem:** Pillow compositing, cache key design, conditional response headers. Visible SEO/social win.

### 9. Color-Palette Extraction + "Browse by Color"
*   **What:** During the existing async variant task, run KMeans/colorthief to store dominant colors as JSONField. New gallery view: pick a color chip, get photos with a similar palette.
*   **Django Ecosystem:** Extends the Celery pipeline, uses JSONField with GIN indexing, custom queryset manager for similarity ranking.

### 10. Backup Verification Pipeline
*   **What:** Celery weekly job: restore the netcup dump to a scratch DB, run sanity queries, assert row counts. Detects silent backup rot.
*   **Django Ecosystem:** Builds on the existing `postgres-backup-cronjob`. Teaches `dbshell`, `loaddata`/`dumpdata` internals, and health-check patterns.

### 11. `django-silk` Query Profiler
*   **What:** Run Silk against the gallery and archive views to find N+1s.
*   **Django Ecosystem:** Almost guaranteed to find query regressions. Teaches reading Django's query log critically and using `select_related`/`prefetch_related` with intent.

### 12. Static-Site Export with `django-distill`
*   **What:** Bake the public site to flat HTML/assets; keep Django running only for the admin.
*   **Django Ecosystem:** Drastically reduces public-facing prod surface and pairs well with the Cloudflare setup. Good architecture lesson in trading dynamism for safety.

---

## Follow-Ups on Previously Open Items

### Full-Text Search — Concrete Plan
*   **What:** Add a `SearchVectorField` on `Post` populated by a `pg_trgm` + `tsvector` generated column (Postgres 12+, Django `GeneratedField` in 5.0+). GIN index on the vector. Search view uses `SearchQuery` with weighted ranks (title A, body B, photo captions C) + trigram similarity for "did you mean."
*   **Django Ecosystem:** One app, multiple PostgreSQL features, no external search server.

### HTMX — Concrete, Non-Toy Examples
*   **In-lightbox prev/next:** swap photo + EXIF panel via `hx-get` + `hx-push-url`, no page reload, deep links still work.
*   **Live markdown preview in admin:** `hx-trigger="keyup changed delay:300ms"` posts the draft, server renders markdown, swaps into a preview pane.
*   **Archive filter chips:** clicking year/camera chip updates the photo list via `hx-target`; browser history preserved via `hx-push-url`.
*   **Lazy EXIF panel:** hover/tap a thumbnail fires `hx-get` to fetch an EXIF partial, revealed without a round-trip page load.
*   **Inline caption edit in admin:** click caption → form appears → save swaps back to text, all via partials.

### Masonry — Reframed for an Archival Site
*   **What:** Skip infinite scroll (wrong shape for an archive). Instead, masonry *within an album* where varying aspect ratios otherwise look poor in a uniform grid. Use native CSS `grid-template-rows: masonry` with a `column-count` fallback — zero JS, no pagination needed because albums are finite.
*   **Django Ecosystem:** Mostly template/CSS work, but exposes you to responsive `srcset` decisions per-aspect-ratio and progressive enhancement patterns.

---



## 1. Core Blog & Photoblog Features

### Tags and Categories (`django-taggit`)
*   **What:** Allow posts and photos to be categorized and tagged for easier browsing.
*   **Django Ecosystem:** Learn to use third-party apps by integrating `django-taggit`. It provides a robust, pre-built tagging engine, demonstrating how pluggable Django apps work.

A. No this site is bespoke and each post is unique. I do not want tagging.

### EXIF Data Extraction & Display
*   **What:** Automatically extract camera settings (Aperture, Shutter Speed, ISO, Focal Length) from uploaded photos and display them on the photoblog.
*   **Django Ecosystem:**
    *   **Pillow (Python Imaging Library):** Work directly with image bits.
    *   **Django Signals (`pre_save` / `post_save`):** Run the extraction logic automatically right before or after an ImageField is saved.

A. We have completed this.

### Threaded Comment System (`django-mptt` or `django-treebeard`)
*   **What:** Allow users to comment on posts with nested replies.
*   **Django Ecosystem:** Relational databases struggle with deep nesting. Using Modified Preorder Tree Traversal (MPTT) teaches you how to efficiently query and template hierarchical tree data in Django.

A. No I dont want to deal with potential abuse of a comment system.

### Full-Text Search (`django.contrib.postgres.search`)
*   **What:** Implement a powerful search bar to quickly find posts by title, content, or tags.
*   **Django Ecosystem:** Move beyond basic `__icontains` queries. If you are using PostgreSQL, this exposes you to `SearchVector`, `SearchQuery`, and `SearchRank` for advanced, weighted full-text searching out-of-the-box.

A. This might be worth looking into.


### RSS Feeds and Sitemaps
*   **What:** Automatically generate XML files so search engines index you better, and readers can subscribe via RSS.
*   **Django Ecosystem:** Teaches `django.contrib.syndication` and `django.contrib.sitemaps`. It’s a great way to learn how Django generates non-HTML responses.

A. I believe this has been implemented

---

## 2. Dynamic Interactions & UI

### Asynchronous Interactions with HTMX
*   **What:** Add "Like/Heart" buttons or dynamic "Load More" pagination that updates without refreshing the page.
*   **Django Ecosystem:** HTMX pairs flawlessly with Django templates. It teaches you how to build modern, dynamic UIs without needing a heavy frontend framework like React, utilizing partial template rendering.


A. I would like more concrete examples of integrating htmx.

### Masonry Gallery with Infinite Scroll
*   **What:** A Pinterest-style staggered image grid for your photoblog that lazily loads more photos as you scroll down.
*   **Django Ecosystem:** Teaches Django’s `Paginator` class and how to serve JSON/partial HTML responses to AJAX requests.

A. I would be open to hearing more about this, but the site is not really meant for current photos. I want to hear more about this idea though.

---

## 3. Advanced Django Architecture

### Image Processing via Background Tasks (Celery + Redis / RabbitMQ)
*   **What:** Generating multiple thumbnails, compressing images, or building WEBP versions can block the web request and slow down uploads. Offload this to a background worker.
*   **Django Ecosystem:** This is a crucial production skill. You'll learn how to set up `Celery`, configure a message broker like Redis, and use `delay()` to handle heavy lifting asynchronously.

A. I think we implemented this.

### Caching (`django.core.cache`)
*   **What:** Speed up your site by caching heavy database queries or entire template fragments (like your photo gallery).
*   **Django Ecosystem:** Connect Django to Redis or Memcached. Learn the difference between site-wide caching, view caching, and low-level cache APIs to optimize database hits.

A. I think we implemented this.

### Build an API (Django REST Framework or Django Ninja)
*   **What:** Expose a read-only JSON API of your posts and photos.
*   **Django Ecosystem:** Very few Django sites are pure HTML nowadays. Building an API teaches you about Serializers, ViewSets, and API routing. This leaves the door open to build a separate mobile app or an advanced React frontend later.

A. Not sure why we would need an API.

### Advanced Authentication (`django-allauth`)
*   **What:** Allow visitors to log in via GitHub, Google, or Twitter if they want to leave a comment or like a post.
*   **Django Ecosystem:** Explores Django's custom User models, external OAuth2 integrations, and managing third-party authentication configurations.

A. I don't know why I would want users to register.

---

## Recommended Next Step
If you want a mix of visual reward and learning, **EXIF extraction via Django Signals** or adding **Tags using `django-taggit`** are fantastic weekend projects to start with!


Implemented.