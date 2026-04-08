# To Do

This backlog is based on the current repo state as of March 20, 2026.

Assumed scope for "feature complete":
- A personal site with a public blog and public photo gallery
- One owner/admin, not a multi-user platform
- Reliable deployment, safe content management, good reader experience, and basic SEO/accessibility
- Advanced community, commerce, AI, and platform ideas are intentionally moved to `FutureResearchNeeded.md`

## P0: Decide the Real Architecture

- [x] Pick one architecture and remove the duplicate path.
  Right now the repo has:
  - `blog/`, which already serves posts and photo albums together
  - `photos/`, which is a second Django app with overlapping album code
  - `docker-compose.yml` and `nginx/nginx.conf`, which only route traffic to the `blog` container
  The first launch task is deciding whether this site is:
  - one Django app with blog at `/` and photos at `/photos/` (Recommended: least operational overhead on a single server, shared templates and admin), or
  - two separately deployed services on `blog.s8njee.com` and `photos.s8njee.com` (Requires separate DBs/auth or shared SSO, and separate static asset pipelines).


A. I choose one Django app with blog at `/` and photos at `/photos/` (Recommended: least operational overhead on a single server, shared templates and admin)


- [x] Align `README.md`, `docker-compose.yml`, nginx, env files, and navigation with the chosen architecture.

A. Done on March 23, 2026. The repo now documents and deploys a single Django site with blog at `/` and photos at `/photos/`, and nginx is templated for one hostname instead of two separate public services.

- [x] Delete or archive the unused implementation after the architecture decision so future work only happens in one place.

A. Done on March 23, 2026. The standalone `photos/` service was archived to `archive/photos-standalone-app/` so active development stays in `blog/`.

## P0: Security And Repo Hygiene

- [ ] Remove committed secrets from the repo and rotate them.
  The repo currently contains environment files with live-looking credentials. Treat all committed secrets as compromised.

  A. In progress on March 23, 2026. The committed env files were removed from the repo and replaced with example files plus ignore rules. Remaining manual follow-up: rotate every previously committed credential in AWS, PostgreSQL, and any deployed host before the next release.

- [x] Add a root `.gitignore` and `.dockerignore`.
  Ignore at least:
  - `.env`
  - `.venv/`
  - `staticfiles/`
  - `media/`
  - `.DS_Store`
  - database dumps and other local-only artifacts

  A. Done on March 23, 2026.

- [x] Replace hardcoded or checked-in runtime config with documented environment variables and example files such as `.env.example`.

A. Done on March 23, 2026. Django now reads documented env files, blank env values fall back cleanly for local SQLite development, and example files were added for Compose, Django, and PostgreSQL config.

- [x] Add a deployment checklist for SSL, DB credentials, media storage, migrations, static collection, and admin bootstrap.

A. Done on March 23, 2026. See `DEPLOYMENT_CHECKLIST.md`.

## P0: Make Deployment Actually Reproducible

- [ ] Ensure the chosen production topology works from a clean machine without manual code edits.

- [x] Move `s8njee` off the shared Netcup PostgreSQL service and onto its own dedicated PostgreSQL 18 instance.
  Reason:
  - `blog.s8njee.com` is currently pointed at `postgres.default.svc.cluster.local`, which is a shared database service used by another app.
  - This is now a proven outage risk. The blog should have its own database service, credentials, and PVC.

  Tomorrow deployment checklist:
  - Create a dedicated PostgreSQL workload for the blog in the `s8njee-web` namespace, ideally as a `StatefulSet` plus a `ClusterIP` service such as `s8njee-postgres`.
  - Use PostgreSQL `18.x` for the new instance. Pin a specific `18.x` image tag instead of `latest` so future deploys stay reproducible.
  - Give the new database its own persistent volume claim and do not reuse the shared `default/postgres` PVC or service.
  - Generate fresh database credentials for `s8njee` only, then update `k8s/overlays/netcup/sealed-secret.yaml` with the new sealed values.
  - Update `k8s/overlays/netcup/configmap.yaml` so `DB_HOST` points to the dedicated service, for example `s8njee-postgres.s8njee-web.svc.cluster.local`.
  - If the new manifest uses direct PostgreSQL bootstrap env vars, include `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` in addition to the app-facing `DB_*` values.
  - Restore the newest backup, not the older local dump. The latest known backup source is `s3://s8njee-photoblog/backups/postgres/netcup/s8njee/latest.json`, which currently points to `backups/postgres/netcup/s8njee/20260401T070007Z-s8njee-daf473e99218.sql.gz`.
  - Prefer restoring with a PostgreSQL 18 client. If the restore target rejects dump header lines like `SET transaction_timeout = 0;` or psql meta-commands such as `\\restrict`, either use a matching/newer client or strip those lines before replaying the dump.
  - Add the same kind of DB wait step used in the `mars` overlay so the Django app does not start before the dedicated database is ready.
  - After cutover, verify:
    - `kubectl logs -n s8njee-web deploy/s8njee-web --tail=200`
    - `curl -I https://blog.s8njee.com`
    - `/` returns `200`
    - `manage.py migrate` succeeds
    - expected row counts exist in `posts_post`, `albums_album`, and `albums_photo`
  - Confirm the backup CronJob is now dumping the dedicated `s8njee` database instead of the shared `default/postgres` service.
  - After the dedicated DB is confirmed healthy, remove the temporary dependency on `postgres.default.svc.cluster.local` from the Netcup overlay docs and config.

- [x] Add one canonical startup path for local development and one for production.
  - Define how and when `manage.py migrate` and `manage.py collectstatic` run during a production release (e.g., via an init container in Docker or deployment script).
  - Clarify the frontend asset pipeline (are we using Webpack/Tailwind, or just vanilla CSS?).

- [x] Verify media and static handling in both local filesystem mode and S3 mode.

- [x] Add backup and restore instructions for:
  - PostgreSQL
  - uploaded media / S3 bucket

- [x] Add basic observability for launch:
  - structured logs
  - error reporting
  - healthcheck / smoke-check steps

## P1: Finish The Core Blog Feature Set

- [ ] Separate `published_at` from `created_at`.
  Posts should support draft creation before publication and preserve a clean publication date.

  

- [ ] Add a richer post authoring format.
  Current posts are plain text in a `TextField`. Choose and implement one of:
  - Markdown with safe rendering (e.g., `python-markdown` + `bleach`)
  - Rich text via the admin (e.g., `django-ckeditor` or `django-tinymce`)
  - **Note:** Decide how inline images within blog posts will be handled (will they be uploaded to S3 natively via the rich text editor, or linked from the `albums` app?).

- [ ] Add post metadata needed for a finished reading experience:
  - excerpt / summary
  - hero image
  - hero image alt text
  - optional subtitle

- [ ] Add previous / next post navigation on post detail pages.

- [ ] Improve archive UX.
  The month archive exists, but it should have an explicit page heading, empty-state handling, and pagination parity with the main index.

- [ ] Add friendly 404 and 500 pages that match the site layout.

- [ ] Add an About page and a clear landing identity for the site owner.
  A personal blog/photo site usually feels incomplete without at least one stable profile/about destination.

## P1: Finish The Core Photo Gallery Feature Set

- [ ] Add human-readable slugs for albums.
  UUID-only URLs work technically, but they are not share-friendly or memorable.

- [ ] Add album cover selection instead of relying on the first related photo.

- [ ] Add per-photo metadata that can be edited cleanly:
  - caption
  - alt text
  - sort order within album

- [ ] Add album and photo management beyond "create + upload".
  The site still needs a safe way to:
  - edit albums
  - rename albums
  - delete albums
  - delete or replace photos
  - reorder photos

- [ ] Improve the upload flow to capture captions and validation at upload time.
  - Implement bulk upload functionality for adding multiple photos simultaneously.
  - Add client-side and server-side validation for file types and size limits.

- [ ] Make the lightbox fully keyboard- and touch-friendly.
  It already works, but it should be treated as a complete feature only after accessibility and mobile interaction are verified.

- [ ] Add dedicated photo permalinks or a shareable deep-link strategy.
  Albums are viewable, but individual photos do not yet have stable, direct URLs.

## P1: Complete The Reader-Facing Cross-Site Experience

- [ ] Make navigation consistent everywhere.
  Blog and photo templates should agree on:
  - URL strategy
  - nav labels
  - canonical links between sections

- [ ] Unify the visual system.
  The current templates are clean but still feel like two adjacent layouts rather than one finished site.

- [ ] Add footer content with copyright, contact/about links, and feed/sitemap access.

- [ ] Verify responsive behavior across:
  - blog list
  - blog detail
  - album grid
  - album detail lightbox
  - upload flow

## P1: SEO, Discovery, And Sharing

- [ ] Add page-level SEO metadata for posts, albums, and the homepage:
  - title templates
  - meta description
  - Open Graph tags
  - social preview images
  - canonical URLs

- [ ] Add `sitemap.xml`.

- [ ] Add `robots.txt`.

- [ ] Add an RSS or Atom feed for blog posts.

- [ ] Decide whether albums should appear in the sitemap and whether private/draft content must be excluded.

## P1: Accessibility And Performance

- [ ] Audit all images for meaningful `alt` behavior.
  Some gallery thumbnails are currently empty-alt or caption-derived.

- [ ] Ensure keyboard focus states and form controls are clearly visible.

- [ ] Improve image delivery with responsive sizes and modern formats where practical.
  - Integrate a CDN (like Cloudflare or AWS CloudFront) to cache heavy static/media files.
  - Implement caching headers (`Cache-Control`) to leverage browser caching.

- [ ] Verify thumbnail generation, large-image handling, and upload limits against real camera-sized files.
  - Decide on a thumbnailing approach: generate on upload (using signals) or on the fly and cache (using libraries like `sorl-thumbnail` or `django-imagekit`). Generating 5-10MB full-resolution images dynamically on every page load will cause severe performance issues.
  - Consider stripping EXIF data during upload processing for privacy and size reduction.

- [ ] Add lazy-loading and pagination or progressive loading where album size could become large.

## P2: Content Management Workflow

- [ ] Decide whether Django admin is the primary authoring interface or whether the site should expose first-party edit screens.

- [ ] If admin stays primary, polish it:
  - better list filters
  - album/photo inline usability
  - bulk actions
  - clearer publish workflow

- [ ] Add explicit draft / published / hidden states where needed for both posts and albums.

- [ ] Document the editorial workflow for creating, previewing, publishing, and correcting content.

## P2: Testing And QA

- [ ] Add automated tests for the blog:
  - post list
  - post detail
  - archive filtering
  - published vs draft visibility

- [ ] Add automated tests for the gallery:
  - album list/detail
  - auth-gated create/upload actions
  - thumbnail generation
  - upload endpoint validation

- [ ] Add storage-related tests for local media and S3-backed media.

- [ ] Add one smoke test for the deployed site routes.

- [ ] Replace the current empty test suites in both apps with meaningful coverage before expanding features further.

## P2: Missing Infrastructure & Security Foundations

- [ ] Add basic rate limiting.
  Protect the `/admin/` login and any upload endpoints against brute-force attacks or abuse (e.g., via `django-ratelimit` or nginx `limit_req`).

- [ ] Automated Backups Strategy.
  While backup scripts were mentioned in P0, ensure there is an automated scheduled task (CRON job) taking routine database dumps (`pg_dump`) and securely offloading them to an offsite location or S3 bucket.

- [ ] Caching Strategy.
  A photo gallery requires heavy caching. Decide if you'll use Django's `cache` framework (with Redis/Memcached) for template fragments or database query caching, as rendering huge galleries dynamically can bottleneck the server.

- [ ] Email Sending & Contact Functionality.
  If the personal site needs error reporting emails (like Django's `ADMINS` via 500 errors) or password resets, configure an SMTP provider (SendGrid, Mailgun) and valid return paths.

## P2: Seed Data And Content Polish

- [ ] Remove placeholder fixture content or replace it with intentional starter content.

- [ ] Decide whether fixtures should exist at all in production startup.
  Loading demo content automatically is useful for a prototype, but risky for a real site.

- [ ] Add a small set of polished launch-ready content:
  - at least a few real posts
  - a few real albums
  - captions / descriptions that demonstrate the final design

## Suggested Execution Order

- [ ] 1. Resolve architecture, secrets, and deployment mismatch first.
- [ ] 2. Finish blog and gallery content models next.
- [ ] 3. Add missing reader-facing features, SEO, and accessibility.
- [ ] 4. Lock in authoring workflow and tests before calling the site complete.
