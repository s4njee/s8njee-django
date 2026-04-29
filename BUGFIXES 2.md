# Bug Fixes

## 2026-04-14

Audited the completed items in `docs/ToDo.md` and fixed the bugs below.

### Photo processing

- Fixed thumbnail generation reading from a closed Django `FieldFile`.
- Impact: eager Celery uploads, EXIF rendering tests, cover selection, and replacement uploads could fail because processing saved intermediate files but then crashed with `ValueError: seek of closed file`.
- Fix: `make_thumbnail_from_image_file()` now reopens/rewinds the file, reads bytes, and builds the thumbnail from an in-memory buffer.

### Photo replacement cleanup

- Fixed stale file cleanup when replacing a photo image.
- Impact: `photo_edit` held mutable `FieldFile` objects before clearing image fields, which made cleanup fragile.
- Fix: capture `(storage, name)` pairs before clearing fields, then delete those concrete stored files after saving the replacement state.

### Album cover management

- Removed the `Set as Album Cover` action from non-ready photo cards.
- Impact: the UI offered an action that the server correctly rejected because album covers must be ready photos with an image.
- Fix: only ready photo cards render the cover action.

### Album slugs

- Fixed blank album slugs colliding under the unique slug constraint.
- Impact: multiple albums with no slug could try to save `""`, causing uniqueness failures even though slugging is optional.
- Fix: `AlbumForm.clean_slug()` now stores blank slugs as `NULL`, allowing multiple un-slugged albums.

### Image alt text

- Fixed gallery image fallbacks that could still render empty `alt` text.
- Impact: completed accessibility work claimed every image had meaningful fallback text, but photos without `alt_text` and captions rendered `alt=""`.
- Fix: album detail and album list images now fall back to the album title, and the lightbox receives `alt_text` in its JSON payload.

### EXIF rendering

- Fixed client-side EXIF rendering to avoid injecting metadata with `innerHTML`.
- Impact: EXIF values come from uploaded image metadata; rendering them as HTML could turn malicious metadata into executable markup.
- Fix: EXIF labels and values are now inserted with `textContent`; the GPS map link is built with DOM APIs and URL encoding.

### Blog publishing dates

- Implemented the completed `published_at` behavior that was documented but missing from the model.
- Impact: posts were still ordered, archived, displayed, and published in feeds by `created_at`, so drafts published later could appear under the wrong date.
- Fix: added `Post.published_at`, set it on first publish, backfilled existing published posts from `created_at`, and updated lists, archives, feeds, templates, context processors, and admin.

### Startup backfills

- Added missing production startup backfills for completed gallery migrations.
- Impact: startup only ran `backfill_photo_sort_order`, leaving album slugs and responsive image variants dependent on manual follow-up.
- Fix: `start.sh` now also runs `backfill_album_slugs` and `backfill_image_variants`.

### Netcup migration staging

- Updated the Netcup migration queue to match completed migrations.
- Impact: `deploy/netcup/migrations/` only staged album migrations `0005` and `0006`, but the code now also needs album migrations `0007`/`0008` and posts migration `0002`.
- Fix: staged:
  - `albums/0007_photo_image_variants.py`
  - `albums/0008_album_slug_photo_alt_text.py`
  - `posts/0002_post_published_at.py`

## Verification

- `uv run python manage.py makemigrations --check --dry-run`
- `uv run python manage.py check`
- `uv run python manage.py test`

Result: all checks passed; 29 tests passed.
