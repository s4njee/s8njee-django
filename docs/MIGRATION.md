# Database Migrations

---

## What a migration is

A **migration** is a Python file that describes a precise change to the database schema — creating a table, adding a column, changing a constraint, or running a data backfill. Django generates these files from your model definitions and applies them in order, so the database schema always stays in sync with the Python code.

### The three commands you use

| Command | What it does |
|---------|--------------|
| `manage.py makemigrations` | Compares the current model code to the last known state and writes a new migration file describing the diff. Run this on your laptop after changing a model. |
| `manage.py migrate` | Applies all unapplied migration files to the database, in order. Run this when deploying or after pulling changes that include new migrations. |
| `manage.py showmigrations` | Lists every migration and marks which ones have been applied (`[X]`) or not (`[ ]`). Useful for verifying the state of a deployed database. |

### How Django tracks what has been applied

Django maintains a table called `django_migrations` in the database. Each row is an `(app, name)` pair — e.g. `("albums", "0003_photo_async_fields")`. When `migrate` runs, it compares the migration files on disk against this table and only runs the files that are missing. If a migration is already recorded it is never re-run.

### Migration files are part of the codebase

Migration files live in `blog/posts/migrations/` and `blog/albums/migrations/`. They are committed to Git. **Do not delete or edit a migration after it has been applied to any database** — Django uses the file as the source of truth for the expected schema state, and removing or modifying it can cause `migrate` to report an inconsistent state or fail.

### Data migrations vs schema migrations

Most migrations only change the schema (add a column, create a table). Some also include a `RunPython` step that fills in data for existing rows — these are called **data migrations**. The backfill runs once, inside the same transaction as the schema change, and has a reverse function so the migration can be unapplied cleanly if needed.

---

## Current migrations

The migrations below are listed in the order they run. Within each app the chain is linear; the two apps (`posts` and `albums`) are independent and their migrations run in parallel.

---

### `posts` app — `blog/posts/migrations/`

#### `0001_initial`

Creates the `posts_post` table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `bigint`, primary key | Auto-incrementing integer |
| `title` | `varchar(200)` | |
| `slug` | `varchar(200)`, unique | URL-safe identifier; unique across all posts |
| `content` | `text` | Raw Markdown source |
| `created_at` | `timestamptz` | Defaults to `now()` at insert time |
| `updated_at` | `timestamptz` | Auto-updated on every save |
| `published` | `boolean` | Controls public visibility |

Default ordering: `ORDER BY created_at DESC`.

#### `0002_post_published_at`

Separates publication date from creation date so a post can be drafted before it goes live.

1. **Schema change** — adds `published_at timestamptz NULL` with a database index.
2. **Data backfill** — for every existing row where `published = true` and `published_at` is `NULL`, sets `published_at = created_at`, so no published post loses its visible date.
3. **Model option change** — switches the default ordering to `ORDER BY published_at DESC, created_at DESC`.

The reverse function sets all `published_at` values back to `NULL`.

---

### `albums` app — `blog/albums/migrations/`

#### `0001_initial`

Creates the `albums_album` and `albums_photo` tables.

**`albums_album`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid`, primary key | `uuid4` generated in Python, not by the DB |
| `title` | `varchar(200)` | |
| `description` | `text` | Optional; blank allowed |
| `created_at` | `timestamptz` | Auto-set at insert |
| `updated_at` | `timestamptz` | Auto-updated on save |

Default ordering: `ORDER BY created_at DESC`.

**`albums_photo`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid`, primary key | `uuid4` generated in Python |
| `image` | `varchar` (file path) | Required; path relative to the storage root |
| `caption` | `varchar(300)` | Optional |
| `uploaded_at` | `timestamptz` | Auto-set at insert |
| `album_id` | `uuid`, FK → `albums_album` | `CASCADE` delete — deleting an album deletes its photos |

Default ordering: `ORDER BY uploaded_at DESC`.

#### `0002_photo_thumbnail`

Adds `thumbnail` to `albums_photo` so the album grid can serve a small pre-cropped image without sending the full-size file.

| Column | Type | Notes |
|--------|------|-------|
| `thumbnail` | `varchar` (file path) | Optional; blank allowed; stored under `photos/%Y/%m/%d/thumbs/` |

#### `0003_photo_async_fields`

Introduces async processing — photos are uploaded first, then processed in a background task. This required making `image` optional (processing fills it in) and adding status tracking.

Schema changes:

| Column | Type | Notes |
|--------|------|-------|
| `original` | `varchar` (file path) | Optional; stores the raw upload before processing (`photos/originals/…`) |
| `status` | `varchar(16)`, indexed | Enum: `pending` / `processing` / `ready` / `failed`; defaults to `pending` |
| `error` | `text` | Populated when `status = failed`; blank otherwise |

`image` and `thumbnail` are both altered to `blank=True` so a row can exist before processing completes.

**Data backfill** — all existing rows (uploaded before async processing existed) are set to `status = ready`. Reverse is a no-op.

#### `0004_photo_exif_data`

Adds a column to store the EXIF metadata extracted from each photo during processing.

| Column | Type | Notes |
|--------|------|-------|
| `exif_data` | `jsonb` | Defaults to `{}`. Stores a flat dict of human-readable label → formatted value pairs, e.g. `{"Camera Model": "NIKON Z6_2", "Shutter": "1/250s"}` |

#### `0005_alter_photo_options_photo_sort_order`

Adds manual ordering so photos within an album can be dragged into a custom sequence.

Schema changes:

| Column | Type | Notes |
|--------|------|-------|
| `sort_order` | `integer unsigned`, indexed | Default `0`; lower value = earlier position |

Default ordering switches from `ORDER BY uploaded_at DESC` to `ORDER BY sort_order ASC, uploaded_at DESC`.

**Data backfill** — assigns `sort_order` values to every existing photo, using the previous implicit order (`uploaded_at DESC`) so nothing visually reorders. Reverse is a no-op.

#### `0006_album_cover_photo`

Lets a specific photo be pinned as the album's cover image, rather than always falling back to the first ready photo.

Schema changes:

| Column | Type | Notes |
|--------|------|-------|
| `cover_photo_id` (on `albums_album`) | `uuid NULL`, FK → `albums_photo` | `SET NULL` on delete — deleting the cover photo clears the field rather than deleting the album |

**Data backfill** — sets `cover_photo` on every existing album to its first ready photo (by `sort_order ASC, uploaded_at DESC`), matching what the fallback logic would have shown. Reverse is a no-op.

#### `0007_photo_image_variants`

Adds two additional size variants so the lightbox can serve a smaller file based on the viewport (`srcset`).

| Column | Type | Notes |
|--------|------|-------|
| `image_medium` | `varchar` (file path) | Optional; 1200px longest edge, stored under `photos/%Y/%m/%d/` |
| `image_small` | `varchar` (file path) | Optional; 800px longest edge, stored under `photos/%Y/%m/%d/` |

No backfill — existing photos get their variants generated by running `manage.py backfill_image_variants` separately.

#### `0008_album_slug_photo_alt_text`

Two independent additions batched into one migration.

| Table | Column | Type | Notes |
|-------|--------|------|-------|
| `albums_album` | `slug` | `varchar(200) NULL UNIQUE` | Optional human-readable URL segment; enables `/photos/s/<slug>/` in addition to the UUID URL |
| `albums_photo` | `alt_text` | `varchar(300)` | Optional; meaningful image description for screen readers and SEO; falls back to `caption` in templates when blank |

No backfill — existing albums retain `slug = NULL` (UUID URL still works); existing photos retain `alt_text = ""` (caption fallback applies).
