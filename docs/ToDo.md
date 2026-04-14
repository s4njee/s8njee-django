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

  A. Done April 2026. `deploy/netcup/migrations/` is the staging area for Django migrations before each Netcup rollout. `DEPLOY.md` documents the copy-stage-verify-clear process and the manual `manage.py migrate` escape hatch.

- [x] Add one canonical startup path for local development and one for production.

  A. Done. `start.sh` runs migrations, backfills, collectstatic, then launches uvicorn.

- [x] Verify media and static handling in both local filesystem mode and S3 mode.

  A. Done.

- [x] Add backup and restore instructions for PostgreSQL and uploaded media / S3 bucket.

  A. Done.

- [x] Add basic observability: structured logs, error reporting, healthcheck / smoke-check steps.

  A. Done.

### Photo Gallery

- [x] Add async photo processing pipeline with status polling.

  A. Done April 2026. `PhotoStatus` state machine (`pending → processing → ready / failed`). Celery task `process_photo` handles RAW/HEIC → AVIF conversion via Pillow + pillow-heif, thumbnail generation, EXIF extraction, and 1920px downscale. Upload endpoint returns 202; client polls `photo_status` until ready. RAW formats supported: NEF, CR2, CR3, DNG, ARW, ORF, RAF, RW2. EXIF stored as JSON and displayed in the lightbox sidebar.

- [x] Add album cover selection instead of relying on the first related photo.

  A. Done April 2026. `Album.cover_photo` ForeignKey (migration 0006). `album_set_cover_photo` view lets staff pick any ready photo. `cover_photo_for_display()` falls back to the first ready photo when none is set.

- [x] Add album and photo management beyond "create + upload".

  A. Done April 2026. Edit/delete album (`album_edit`, `album_delete`). Edit caption or replace image (`photo_edit`). Delete photo with file cleanup (`photo_delete`). Drag-to-reorder with `photo_reorder` API. `Photo.delete_files()` cleans up all storage files. All actions are `@staff_member_required`.

- [x] Add per-photo metadata that can be edited cleanly.

  A. Done April 2026. Caption editable via `photo_edit`. Sort order managed via drag-and-drop, persisted via `photo_reorder` API (migration 0005). Note: dedicated alt text field not yet added; lightbox derives alt from caption.

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

  A. Done April 2026. `@media (max-width: 640px)` stacks the sidebar below the image. Desktop collapsibility (toggle button) is a separate open item.

---

## Open

### P0: Security

- [ ] Remove committed secrets from the repo and rotate them.
  Env files were removed and replaced with examples, but every previously committed credential (AWS, PostgreSQL, deployed host) still needs to be rotated before the next release.

### P1: Blog

- [ ] Separate `published_at` from `created_at`.
  Posts should support draft creation before publication and preserve a clean publication date.

- [ ] Add a richer post authoring format.
  Current posts are plain text in a `TextField`. Choose one:
  - Markdown with safe rendering (`python-markdown` + `bleach`)
  - Rich text via the admin (`django-ckeditor` or `django-tinymce`)
  - Decide how inline images are handled (S3 via editor, or linked from the albums app).

- [ ] Add post metadata needed for a finished reading experience:
  - excerpt / summary
  - hero image + alt text
  - optional subtitle

- [ ] Add previous / next post navigation on post detail pages.

- [ ] Improve archive UX.
  The month archive needs an explicit heading, empty-state handling, and pagination parity with the main index.

- [ ] Add friendly 404 and 500 pages that match the site layout.

- [ ] Add an About page and a clear landing identity.

### P1: Photo Gallery

- [ ] Add human-readable slugs for albums.
  UUID-only URLs are not share-friendly or memorable.

- [ ] Improve the upload flow.
  - Captions at upload time: not yet implemented — captions are added after upload via photo_edit.
  - Bulk upload UI exists with async per-file progress; cancellation is a separate open item below.

### P1: Cross-Site Experience

- [ ] Make navigation consistent everywhere.
  Blog and photo templates should agree on URL strategy, nav labels, and canonical links between sections.

- [ ] Unify the visual system.
  The current templates are clean but still feel like two adjacent layouts rather than one finished site.

- [ ] Add footer content with copyright, contact/about links, and feed/sitemap access.

- [ ] Verify responsive behavior across blog list, blog detail, album grid, album detail lightbox, and upload flow.

### P1: SEO, Discovery, And Sharing

- [ ] Add page-level SEO metadata for posts, albums, and the homepage:
  - title templates, meta description, Open Graph tags, social preview images, canonical URLs

- [ ] Add `sitemap.xml`.

- [ ] Add `robots.txt`.

- [ ] Add an RSS or Atom feed for blog posts.

- [ ] Decide whether albums appear in the sitemap and whether draft content must be excluded.

### P1: Accessibility And Performance

- [ ] Audit all images for meaningful `alt` text.
  Gallery thumbnails are currently empty-alt or caption-derived; a dedicated alt text field on `Photo` is the right fix.

- [ ] Ensure keyboard focus states and form controls are clearly visible.

- [ ] Integrate a CDN and set `Cache-Control` headers for media files.

- [ ] Add lazy-loading and pagination or progressive loading for large albums.

### P2: Photo Gallery Polish

- [ ] Preserve original files after processing (or make it opt-in).
  The original RAW/HEIC is currently deleted after AVIF generation. Add a `keep_original` flag or an admin download action.

- [ ] Add upload cancellation.
  Once a file starts uploading there is no way to abort it.

- [x] Add EXIF sidebar desktop toggle.

  A. Done April 2026. `◀ EXIF` / `EXIF ▶` button positioned top-left of the lightbox (mirrors the close button at top-right). Clicking toggles a `.exif-collapsed` class on `#lightbox-shell`, which collapses the grid column and hides the `<aside>`. The `#lb-img` max-width is CSS-driven so it expands to fill the freed space without any inline style juggling. Preference saved to `localStorage` and restored on each `openLightbox()`. Button hidden on mobile via `@media (max-width: 640px)` since the sidebar already stacks below the image there.

- [ ] Fix the GPS "Available" indicator.
  Either display the coordinates (and optionally a small map), or omit the field when no coordinates are surfaced.

- [ ] Expand EXIF display fields.
  Professional sites (Flickr, 500px) also surface white balance, metering mode, flash, color space, and lens ID.

- [ ] Add watermark support.
  Configurable text or logo overlay applied during image processing, with a per-album enable flag.

- [ ] Add tagging and cross-album collections.
  Add tags to photos so content can be browsed across albums.

- [ ] Show photo count on the album list page.

### P2: Content Management

- [ ] Decide whether Django admin is the primary authoring interface or whether the site needs first-party edit screens.

- [ ] If admin stays primary: better list filters, album/photo inline usability, bulk actions, clearer publish workflow.

- [ ] Add explicit draft / published / hidden states for both posts and albums.

- [ ] Document the editorial workflow for creating, previewing, publishing, and correcting content.

### P2: Testing And QA

- [ ] Add automated tests for the blog: post list, post detail, archive filtering, published vs draft visibility.

- [ ] Add automated tests for the gallery: album list/detail, auth-gated actions, thumbnail generation, upload endpoint validation.

- [ ] Add storage-related tests for local media and S3-backed media.

- [ ] Add one smoke test for the deployed site routes.

### P2: Infrastructure & Security

- [ ] Add basic rate limiting on `/admin/` login and upload endpoints.

- [ ] Automate database backups via a scheduled CronJob dumping to S3.

- [ ] Decide on a caching strategy (Redis/Memcached for template fragments or query caching).

- [ ] Configure SMTP for error-reporting emails and password resets.

### P2: Content

- [ ] Remove placeholder fixture content or replace with intentional starter content.

- [ ] Decide whether fixtures run at all on production startup.

- [ ] Add polished launch-ready content: real posts, real albums with captions.
