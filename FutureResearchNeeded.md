# Future Research Needed

These ideas are intentionally outside the core "functional personal blog/photo site" scope. They may be worth exploring after the main site is stable, secure, and feature complete.

## Audience And Community Features

- Comments or guestbook
  Research needed:
  - self-hosted vs third-party moderation
  - spam protection
  - whether this site should stay read-only

- Newsletter or email subscriptions
  Research needed:
  - provider choice
  - signup UX
  - privacy and consent requirements

- Reader accounts, favorites, or saved albums
  Research needed:
  - whether there is any real need for user accounts on a personal site
  - account recovery, moderation, and support overhead

## Advanced Discovery

- Full-text search across posts and photo captions
  Research needed:
  - database search vs external search service
  - indexing strategy
  - relevance tuning for small sites

- Related-post recommendations
  Research needed:
  - manual curation vs automatic tagging
  - whether enough content volume exists to justify it

- Advanced analytics
  Research needed:
  - privacy-friendly analytics providers
  - what decisions the data would actually drive

## Advanced Photo Features

- EXIF-powered camera, lens, map, and timeline views
  Research needed:
  - metadata extraction pipeline
  - privacy concerns around location data
  - storage/indexing for search and filtering

- Smart albums or tag-based collections
  Research needed:
  - tagging model
  - manual vs automatic categorization
  - UI complexity for browse/filter flows

- AI-assisted captioning or tagging
  Research needed:
  - model/provider choice
  - cost control
  - privacy and review workflow

- Video support alongside photo albums
  Research needed:
  - storage cost
  - transcoding pipeline
  - player and CDN requirements

## Monetization And Commercial Extensions

- Print sales or digital licensing
  Research needed:
  - storefront approach
  - tax/payment handling
  - watermarking and fulfillment workflow

- Sponsored posts, portfolio bookings, or lead forms
  Research needed:
  - whether the site is becoming a portfolio/business property instead of a personal journal

## Platform And Architecture Experiments

- Headless API for mobile apps or alternate frontends
  Research needed:
  - REST vs GraphQL
  - auth model
  - versioning and maintenance cost

- Native app or serious PWA support
  Research needed:
  - offline caching strategy
  - notification model
  - whether usage patterns justify the effort

- Multi-author or multi-tenant support
  Research needed:
  - permissions model
  - editorial workflow
  - data isolation concerns

- Federation or social publishing hooks
  Research needed:
  - ActivityPub / fediverse compatibility
  - cross-posting workflow
  - moderation implications

## Design And Storytelling Experiments

- Longform visual essays that mix posts, galleries, maps, and embedded media
  Research needed:
  - reusable page-builder model vs handcrafted templates
  - editorial workflow for mixed-media storytelling

- Time-based homepage concepts such as "recent life", "this month", or "on this day"
  Research needed:
  - whether the site wants to stay archival or become more dynamic and diary-like

- Seasonal or project-specific visual themes
  Research needed:
  - how far the design system should bend without becoming hard to maintain

## Advanced Django Ecosystem & Robustness

- Background task processing for heavy operations
  Research needed:
  - Celery vs. Django-Q vs. Huey for handling image resizing, video transcoding, or bulk emails.
  - Redis vs. RabbitMQ as a message broker.

- Deep caching strategies
  Research needed:
  - Using `django-redis` for template fragment caching (especially for large photo galleries).
  - Per-view caching vs. database-level query caching.
  - Cache invalidation strategies when albums are updated.

- Enhanced security and rate limiting
  Research needed:
  - `django-axes` or `django-defender` for locking out brute-force admin login attempts.
  - Implementing strict Content Security Policy (CSP) headers via `django-csp`.

- Application observability and health checks
  Research needed:
  - Integrating `django-health-check` for deep liveness probes (checking DB, cache, and S3 connectivity) during deployment.
  - `django-prometheus` or Sentry APM for tracking database query performance and view latency.

- Database and ORM optimization at scale
  Research needed:
  - Advanced usage of `select_related` and `prefetch_related` to eliminate N+1 queries in complex photo feeds.
  - Read-replica database routing for read-heavy blog traffic.
  - Migrating default integer primary keys to UUIDs for security and distributed systems compatibility.

- Advanced testing ecosystem
  Research needed:
  - Migrating from standard `unittest` to `pytest-django` for more concise tests.
  - Using `factory_boy` for generating robust randomized test data instead of static JSON fixtures.

## When To Revisit This File

Move items from this file into `ToDo.md` only after:
- the deployment path is stable
- secrets and repo hygiene are fixed
- blog and album workflows are complete
- tests cover the core publishing and gallery flows
