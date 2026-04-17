# To Do

Assumed scope for "feature complete":
- A personal site with a public blog and public photo gallery
- One owner/admin, not a multi-user platform
- Reliable deployment, safe content management, good reader experience, and basic SEO/accessibility
- Advanced community, commerce, AI, and platform ideas are intentionally moved to [`FutureResearchNeeded.md`](FutureResearchNeeded.md)

---

## Completed

### Architecture

- [x] Pick one architecture and remove the duplicate path.

  A. Chose one Django app with blog at `/` and photos at `/photos/`.

- [x] Align `README.md`, `docker-compose.yml`, nginx, env files, and navigation with the chosen architecture.

  A. Done March 2026. Repo documents and deploys a single Django site; nginx is templated for one hostname.

- [x] Delete or archive the unused implementation.

  A. Done March 2026. Standalone `photos/` service archived to `archive/photos-standalone-app/`.

### Repo Hygiene

- [x] Add a root `.gitignore` and `.dockerignore`.

  A. Done March 2026.

- [x] Replace hardcoded or checked-in runtime config with documented environment variables and example files.

  A. Done March 2026. Django reads documented env files; blank values fall back cleanly for local SQLite dev.

- [x] Add a deployment checklist for SSL, DB credentials, media storage, migrations, static collection, and admin bootstrap.

  A. Done March 2026. See [`DEPLOYMENT_CHECKLIST.md`](DEPLOYMENT_CHECKLIST.md).

### Deployment

- [x] Move `s8njee` off the shared Netcup PostgreSQL service and onto its own dedicated PostgreSQL 18 instance.

  A. Done. Dedicated PostgreSQL 18 StatefulSet created in the `s8njee-web` namespace with its own PVC and sealed credentials.

- [x] Document Netcup migration staging workflow.

  A. Done April 2026. `deploy/netcup/migrations/` is the staging area for Django migrations before each Netcup rollout. `DEPLOY.md` documents the copy-stage-verify-clear process and the manual `manage.py migrate` escape hatch. Currently staged: `albums/0005` through `albums/0008`.

- [x] Add one canonical startup path for local development and one for production.

  A. Done. `start.sh` runs migrations, backfills, collectstatic, then launches uvicorn.

- [x] Verify media and static handling in both local filesystem mode and S3 mode.

  A. Done.

- [x] Add backup and restore instructions for PostgreSQL and uploaded media / S3 bucket.

  A. Done.

- [x] Add basic observability: structured logs, error reporting, healthcheck / smoke-check steps.

  A. Done.

### Blog

- [x] Add a richer post authoring format.

  A. Done April 2026. Markdown with `python-markdown` + `nh3` sanitizer. Toast UI editor with live preview panel in the staff editor (`/editor/posts/`). Toolbar includes image upload to `blog-images/` in the storage backend.

- [x] Separate `published_at` from `created_at`.

  A. Done April 2026. `Post` has `published_at` set on first publish; `created_at` and `updated_at` are auto-managed. Editor shows a **Publish this post to the public site** toggle; drafts are invisible to the public.

### Photo Gallery

- [x] Add async photo processing pipeline with status polling.

  A. Done April 2026. `PhotoStatus` state machine (`pending → processing → ready / failed`). Celery task `process_photo` handles RAW/HEIC → AVIF conversion via Pillow + pillow-heif, thumbnail generation, EXIF extraction, and 1920px downscale. Upload endpoint returns 202; client polls `photo_status` until ready. RAW formats supported: NEF, CR2, CR3, DNG, ARW, ORF, RAF, RW2. EXIF stored as JSON and displayed in the lightbox sidebar.

- [x] Add album cover selection instead of relying on the first related photo.

  A. Done April 2026. `Album.cover_photo` ForeignKey (migration 0006). `album_set_cover_photo` view lets staff pick any ready photo. `cover_photo_for_display()` falls back to the first ready photo when none is set.

- [x] Add album and photo management beyond "create + upload".

  A. Done April 2026. Edit/delete album (`album_edit`, `album_delete`). Edit caption or replace image (`photo_edit`). Delete photo with file cleanup (`photo_delete`). Drag-to-reorder with `photo_reorder` API. `Photo.delete_files()` cleans up all storage files. All actions are `@staff_member_required`.

- [x] Add per-photo metadata that can be edited cleanly.

  A. Done April 2026. Caption and `alt_text` editable via `photo_edit`. Sort order managed via drag-and-drop, persisted via `photo_reorder` API (migration 0005).

- [x] Make the lightbox fully keyboard- and touch-friendly.

  A. Done April 2026. `role="dialog"`, `aria-modal`, `aria-label`, `tabindex="-1"` on the container. Close `<div>` replaced with a `<button>` with `aria-label`. Focus moves into the dialog on open and returns to the triggering card on close. Tab/Shift+Tab trapped within the lightbox buttons. Touch swipe (≥40px horizontal) navigates photos via passive listeners. `@media (max-width: 640px)` stacks the EXIF sidebar below the image.

- [x] Add dedicated photo permalinks / shareable deep-link strategy.

  A. Done April 2026. Lightbox writes `#photo-{uuid}` to the URL hash (was positional `#photo-{index}`, which broke after reordering). Hash restore on page load uses UUID lookup. "Copy link" button in the sidebar copies the full URL to clipboard with `execCommand` and `window.prompt` fallbacks. Server-side route `GET /albums/{album_pk}/photos/{photo_pk}/` redirects to `album_detail#photo-{uuid}`.

- [x] Enable parallel uploads.

  A. Done April 2026. `startUpload` runs up to 3 concurrent uploads via a shared-index worker pool. Each slot calls `await uploadOne(item)` and pulls the next pending item when done. Per-file progress and status update independently. Retry allowed while the batch is active.

- [x] Preload adjacent images in the lightbox.

  A. Done April 2026. `preloadAdjacentPhotos()` called at the end of every `showPhoto()`. Uses `<link rel="preload" imagesrcset imagesizes>` so the browser prefetches the same variant it will select for the `<img srcset>`, not always the full-size file. A module-level `preloaded` Set prevents duplicate requests.

- [x] Add image variants with responsive `srcset`.

  A. Done April 2026. `Photo` gains `image_medium` (1200px) and `image_small` (800px) fields (migration 0007). Celery task generates both variants from the full-size image bytes after processing. View includes `url_medium` and `url_small` in the JSON payload. Lightbox sets `srcset` and `sizes` on every `showPhoto()` call; falls back gracefully to `src`-only for photos without variants. Run `manage.py backfill_image_variants` for existing photos.

- [x] Align EXIF formatting with photography conventions.

  A. Done April 2026. `50mm` not `50 mm`, `1/250s` not `1/250 s`. `f/2.8` was already correct.

- [x] Make the EXIF sidebar usable on mobile.

  A. Done April 2026. `@media (max-width: 640px)` stacks the sidebar below the image.

- [x] Add EXIF sidebar desktop toggle.

  A. Done April 2026. `◀ EXIF` / `EXIF ▶` button positioned top-left of the lightbox (mirrors the close button at top-right). Clicking toggles a `.exif-collapsed` class on `#lightbox-shell`, which collapses the grid column and hides the `<aside>`. The `#lb-img` max-width is CSS-driven so it expands to fill the freed space without any inline style juggling. Preference saved to `localStorage` and restored on each `openLightbox()`. Button hidden on mobile via `@media (max-width: 640px)` since the sidebar already stacks below the image there.

- [x] Add human-readable slugs for albums.

  A. Done April 2026. `Album.slug` SlugField (nullable). Albums accessible at `/photos/s/<slug>/` in addition to UUID URL. Slug set via the create/edit album form. `Album.get_absolute_url()` prefers the slug URL when available.

- [x] Fix the GPS "Available" indicator.

  A. Done April 2026. `image_processing.py` now outputs decimal-degree coordinates (`48.8566° N, 2.3522° E`). Lightbox sidebar renders GPS as a Google Maps link when coordinates are present.

### SEO, Discovery, And Sharing

- [x] Add `sitemap.xml`.

  A. Done April 2026. `PostSitemap`, `AlbumSitemap`, and `StaticViewSitemap` in `posts/sitemaps.py`. Registered at `/sitemap.xml` in root `urls.py`.

- [x] Add `robots.txt`.

  A. Done April 2026. Template at `templates/robots.txt`, served at `/robots.txt`. Points to `/sitemap.xml`.

- [x] Add an RSS or Atom feed for blog posts.

  A. Done April 2026. `LatestPostsFeed` in `posts/feeds.py`, registered at `/feed/`. Linked from the site footer and `<link rel="alternate">` in the base template.

- [x] Add page-level SEO metadata for posts and albums (OG tags, meta description).

  A. Done April 2026. `base.html` has `{% block og_* %}` / `{% block meta_description %}` blocks. Blog post detail and album detail templates override title, description, and `og:image`.

### Cross-Site Experience

- [x] Make navigation consistent everywhere.

  A. Done April 2026. Shared `base.html` used by both blog and albums apps. Nav includes blog home, photos, and staff-only create links.

- [x] Unify the visual system.

  A. Done April 2026. Single shared stylesheet (`static/css/style.css`) referenced from `base.html`. Both apps inherit the same typography, spacing, and component styles.

- [x] Add footer content with copyright, contact/about links, and feed/sitemap access.

  A. Done April 2026. Footer in `base.html` includes copyright year, sitemap link, and RSS feed link.

### Accessibility And Performance

- [x] Audit all images for meaningful `alt` text.

  A. Done April 2026. `Photo.alt_text` CharField added (migration). Photo edit form exposes the field. Templates use `alt_text|default:caption` so every `<img>` has a non-empty alt.

- [x] Add lazy-loading for gallery images.

  A. Done April 2026. `loading="lazy"` on album grid thumbnails and blog post images.

### Photo Gallery Polish

- [x] Show photo count on the album list page.

  A. Done April 2026. Album list cards show `{{ album.photos.count }} photo{{ album.photos.count|pluralize }}`.

### Content Management

- [x] Document the editorial workflow for creating, previewing, publishing, and correcting content.

  A. Done April 2026. See [`EDITORIAL.md`](EDITORIAL.md). Covers blog post drafting, live preview, publishing, slug changes, image embedding, and album/photo management (upload, captions, alt text, reorder, cover, replace, delete, permalinks). Also explicitly documents current limitations: no album drafts, no scheduled publishing, no preview URL for unpublished posts, no version history.

---

## Open

### P0: Security

- [ ] Remove committed secrets from the repo and rotate them.
  Env files were removed and replaced with examples, but every previously committed credential (AWS, PostgreSQL, deployed host) still needs to be rotated before the next release.

### P1: Blog

- [ ] Add post metadata needed for a finished reading experience:
  - excerpt / summary
  - hero image + alt text
  - optional subtitle

- [x] Add previous / next post navigation on post detail pages.

  A. Done April 2026. `PostDetailView.get_context_data()` adds `previous_post` (older, lower `published_at`) and `next_post` (newer, higher `published_at`). `post_detail.html` renders a two-column `<nav class="post-nav">` between the article and the back link.

- [x] Improve archive UX.

  A. Done April 2026. `PostMonthArchiveView.get_context_data()` adds `archive_label` (e.g. "April 2026"). `post_list.html` renders an `<h2 class="archive-heading">` when the label is present, sets a matching page title, and shows "No posts in April 2026." as the empty state instead of the generic "No posts yet."

- [x] Add friendly 404 and 500 pages that match the site layout.

  A. Done April 2026. `templates/404.html` and `templates/500.html` both extend `base.html`. Custom `handler404` and `handler500` views in `posts/views.py` render them with full request context (so the nav, footer, and sidebar work). `handler500` is registered in `blog/urls.py`; `archive_months` context processor wrapped in try/except so a DB failure during a 500 doesn't cascade.

- [ ] Add an About page and a clear landing identity.

### P1: Photo Gallery

- [ ] Improve the upload flow.
  - Captions at upload time: not yet implemented — captions are added after upload via photo_edit.
  - Bulk upload UI exists with async per-file progress; cancellation is a separate open item below.

### P1: SEO, Discovery, And Sharing

- [ ] Add canonical URLs to page-level SEO metadata.
  OG tags and meta descriptions are done; `<link rel="canonical">` is not yet set.

- [ ] Decide whether albums appear in the sitemap and whether draft content must be excluded.

### P1: Accessibility And Performance

- [ ] Ensure keyboard focus states and form controls are clearly visible.

- [ ] Integrate a CDN and set `Cache-Control` headers for media files.

- [ ] Add pagination or progressive loading for large albums.
  `loading="lazy"` is set on thumbnails; server-side pagination of the album grid is not yet implemented.

### P2: Photo Gallery Polish

- [ ] Preserve original files after processing (or make it opt-in).
  The original RAW/HEIC is currently deleted after AVIF generation. Add a `keep_original` flag or an admin download action.

- [ ] Add upload cancellation.
  Once a file starts uploading there is no way to abort it.

- [ ] Expand EXIF display fields.
  Professional sites (Flickr, 500px) also surface white balance, metering mode, flash, color space, and lens ID.

- [ ] Add watermark support.
  Configurable text or logo overlay applied during image processing, with a per-album enable flag.

- [ ] Add tagging and cross-album collections.
  Add tags to photos so content can be browsed across albums.

### P2: Content Management

- [ ] Decide whether Django admin is the primary authoring interface or whether the site needs first-party edit screens.

- [ ] If admin stays primary: better list filters, album/photo inline usability, bulk actions, clearer publish workflow.

- [ ] Add explicit draft / published / hidden states for albums.
  Posts already have draft/published. Albums are public the moment they are created.

### P2: Refactoring

- [ ] Switch album CRUD views to CBVs.
  `album_create`, `album_edit`, and `album_delete` in `blog/albums/views.py` are FBVs, while `AlbumListView` is a CBV. Convert to `CreateView` / `UpdateView` / `DeleteView` (with a `StaffRequiredMixin`) so the app uses one convention.

- [ ] Version the album cache keys to force invalidation on schema changes.
  `_get_album_detail_payload` in `blog/albums/views.py` currently detects stale cache entries by checking whether the first photo payload contains `permalink_url` — fragile and only catches that one specific shape change. Bake a version suffix into `ALBUM_LIST_CACHE_KEY` and `get_album_detail_cache_key` (e.g. `album_detail_v2_{pk}`); bumping the version in `blog/albums/cache_keys.py` then invalidates every stored payload atomically. Delete the ad-hoc staleness check once versioning is in place.

### P2: Testing And QA

- [ ] Add automated tests for the blog: post list, post detail, archive filtering, published vs draft visibility.

- [ ] Add automated tests for the gallery: album list/detail, auth-gated actions, thumbnail generation, upload endpoint validation.

- [ ] Add storage-related tests for local media and S3-backed media.

- [ ] Add one smoke test for the deployed site routes.

### P2: Infrastructure & Security

- [ ] Add basic rate limiting on `/admin/` login and upload endpoints.

- [ ] Automate database backups via a scheduled CronJob dumping to S3.

- [ ] Decide on a caching strategy (Redis/Memcached for template fragments or query caching).
  See [`docs/implementation/CACHE.md`](implementation/CACHE.md) for the implementation plan and open design questions.

- [ ] Configure SMTP for error-reporting emails and password resets.

### P2: Content

- [x] Remove placeholder fixture content or replace with intentional starter content.

  A. Done April 2026. Removed the old `initial_content.json` test fixture and refreshed `seed_content.json` from the current Netcup production content at `blog.s8njee.com`: 22 posts, 14 albums, and 704 photos. The fixture is normalized for the current schema with `published_at`, album slugs, ready photo status, sort order, alt text, and image-variant defaults.

- [ ] Decide whether fixtures run at all on production startup.

- [ ] Add polished launch-ready content: real posts, real albums with captions.

## bugs

- [ ] **Fix empty default Open Graph title/description values**  
  **Delegate to:** SEO/templating agent  
  `blog/templates/base.html` uses `{{ self.title }}` and `{{ self.meta_description }}` inside OG default blocks, which can render empty values on pages that do not override OG blocks (e.g. list pages and error pages). Replace with explicit safe defaults.

- [ ] **Use absolute URLs for OG images**  
  **Delegate to:** SEO agent  
  OG images in `blog/templates/base.html` and `blog/albums/templates/albums/album_detail.html` are rendered as relative paths; social crawlers typically expect absolute URLs. Build absolute media/static URLs using request context.

- [ ] **Avoid duplicate album detail URL variants in photo permalinks**  
  **Delegate to:** routing/SEO agent  
  `photo_permalink` in `blog/albums/views.py` always redirects to the PK route, even when an album slug exists. This creates duplicate entry URLs and weakens the slug-based URL strategy.

- [ ] **Fix N+1 photo-count queries on album list**  
  **Delegate to:** backend performance agent  
  `blog/albums/templates/albums/album_list.html` uses `album.photos.count` per card; this can trigger per-album count queries. Move to `annotate(photo_count=...)` in `AlbumListView` and render `album.photo_count`.

- [ ] **Harden RSS descriptions for feed readers**  
  **Delegate to:** syndication agent  
  `LatestPostsFeed.item_description` returns `mark_safe(item.rendered_content)` directly in `blog/posts/feeds.py`; this can produce inconsistent rendering in strict feed readers. Add feed-safe description output (sanitized/normalized HTML or plaintext summary fallback).
