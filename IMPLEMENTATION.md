# Django Implementation Plan For `s8njee-web`

This document turns the practices from `STUDY_GUIDE.md` into a project-specific implementation roadmap for this repository.

The goal is not just to ship features. The goal is to use this site as a serious Django training ground, where each feature teaches a real part of the framework: models, routing, forms, admin, auth, testing, deployment, performance, and background-friendly maintenance tasks.

The current project already has a good base:

- A split settings package in `blog/blog/settings/`
- Separate Django apps for `posts` and `albums`
- Class-based and function-based views
- Auth routes under `/accounts/`
- Admin registration for existing models
- Local SQLite and production PostgreSQL paths
- S3-backed media support in production

What follows is a recommended expansion plan that stays aligned with your personal site while pushing deeper into Django fundamentals.

## Guiding Direction

Instead of keeping the site limited to a blog plus photo gallery, expand it into a personal publishing platform with a few adjacent domains:

- Writing: blog posts, notes, drafts, series, tags
- Photography: albums, photos, EXIF-aware organization, featured shots
- Projects: software projects, case studies, changelogs, release notes
- Presence: about page, now page, uses page, contact page
- Curation: reading list, bookmarks, recommendations, collected links
- Community-lite: guestbook, reactions, comments, newsletter signup
- Operations: editorial workflow, dashboards, import/export, backups

This broader scope is useful because Django gets much more interesting when the site has several related apps instead of one content type.

## How To Use This Plan

Each section below includes:

- What to build
- Which study-guide practices it reinforces
- Why it is a good fit for this repository
- Suggested implementation notes

The sections are ordered so early work builds fundamentals and later work adds depth.

## Phase 1: Tighten The Foundations

These items are not flashy, but they build confidence with the exact mechanics Django uses every day.

### 1. Settings And Configuration Audit

Status now:

- Already using `base.py`, `development.py`, and `production.py`
- `manage.py` defaults to `blog.settings.development`
- Environment loading is handled manually with `python-dotenv`

Recommended work:

- Add `testing.py` under `blog/blog/settings/`
- Make test settings use fast password hashing, local memory email backend, and SQLite
- Add a dedicated `DJANGO_SETTINGS_MODULE` section to `README.md` or `DEV.md`
- Run `manage.py check --deploy --settings=blog.settings.production` as a documented release step
- Consider replacing the custom env helpers with `django-environ` later, but only after you fully understand the current setup

Study guide coverage:

- Settings architecture
- Environment variables
- `DEBUG`, `ALLOWED_HOSTS`, `SECRET_KEY`
- `manage.py` vs `django-admin`

Why it matters here:

This repo already has the right shape, so the win is in making the configuration more explicit and production-safe instead of starting from scratch.

### 2. URL Namespacing Cleanup

Status now:

- Root URLs include `posts.urls` and `albums.urls`
- Route names are global
- `app_name` is not defined in the app URLconfs

Recommended work:

- Add `app_name = "posts"` and `app_name = "albums"`
- Update all `reverse()` calls, redirects, and templates to use namespaced URLs
- Keep route ownership per app
- Add a small `core` app for static pages like home, about, now, and contact

Study guide coverage:

- URL namespacing
- `reverse()` and `reverse_lazy()`
- Nested includes
- `path()` usage

Why it matters here:

This becomes more important as soon as you add `projects`, `guestbook`, or `reading` apps with their own `detail` and `list` views.

### 3. Create A `core` App

Build:

- Home page
- About page
- Now page
- Uses / setup page
- Contact page

Recommended model choices:

- Start with template views only
- Then migrate selected pages to database-backed content with a `Page` model

Study guide coverage:

- App structure
- CBVs
- Template organization
- Admin registration

Why it matters here:

A `core` app gives you a clean home for site-wide behavior instead of overloading `posts`.

## Phase 2: Improve The Content Model

The current `Post` model is intentionally small. That is a good starting point, but it leaves a lot of Django model practice available.

### 4. Expand `Post` Into A Real Publishing Model

Current fields:

- `title`
- `slug`
- `content`
- `created_at`
- `updated_at`
- `published`

Recommended additions:

- `status` with choices: draft, scheduled, published, archived
- `published_at`
- `summary`
- `hero_image`
- `seo_title`
- `seo_description`
- `is_featured`
- `reading_time_minutes`

Implementation notes:

- Replace the boolean `published` with a `TextChoices` status field
- Use `clean()` to enforce rules like `published_at` being required for published posts
- Add database indexes for `status`, `slug`, and `published_at`
- Keep `get_absolute_url()` as the canonical path builder

Study guide coverage:

- Model fields
- `choices` / `TextChoices`
- model validation via `clean()`
- indexes and constraints
- migrations

Why it matters here:

This is the first real step from tutorial blog to content platform.

### 5. Add Tags, Series, And Categories

Build:

- `Tag`
- `Series`
- optional `Category`

Suggested relationships:

- `Post.tags = ManyToManyField(Tag, related_name="posts")`
- `Post.series = ForeignKey(Series, null=True, blank=True, related_name="posts")`
- `Photo.tags = ManyToManyField(Tag, blank=True, related_name="photos")`

Implementation notes:

- Add slug fields to `Tag` and `Series`
- Build list and detail pages for tags and series
- Add sidebar sections for related content
- Consider reusing tags across writing, projects, and photos for a cross-site taxonomy

Study guide coverage:

- `ManyToManyField`
- `ForeignKey`
- `related_name`
- filtering across relationships
- `prefetch_related()`

Why it matters here:

Shared taxonomy is a great Django exercise because it touches models, admin, forms, templates, and query optimization.

### 6. Add A `Project` App

This is one of the best expansions for a personal site.

Build:

- `Project` model
- `ProjectLink` model for GitHub, live demo, docs, write-up
- optional `ProjectUpdate` or `ChangelogEntry` model

Suggested fields:

- `name`
- `slug`
- `summary`
- `description`
- `status`
- `started_on`
- `ended_on`
- `tech_stack`
- `featured`
- `repository_url`
- `live_url`

Possible relationships:

- `Project.posts` through a linking model or reverse relation from posts
- `Project.photos` as gallery images
- `Project.tags`

Study guide coverage:

- one-to-many relations
- many-to-many relations
- custom admin
- richer list/detail views
- ordering and filtering

Why it matters here:

It broadens the site naturally and creates a second serious domain model besides blogging.

## Phase 3: Lean Into Django Forms And Admin

Your current post editor is already a strong learning foothold. This phase deepens that.

### 7. Build A Better Editorial Workflow

Build:

- Draft list for staff
- Scheduled posts
- Unpublished preview tokens
- Publish/unpublish actions in admin

Implementation notes:

- Add custom manager/queryset methods like `published()` and `visible_to(user)`
- Move post filtering logic out of raw `filter(published=True)` calls into reusable queryset methods
- Add custom admin actions: publish selected, unpublish selected, archive selected
- Add `ModelAdmin` filters for status, tags, series, and featured state

Study guide coverage:

- custom managers and querysets
- admin customization
- permissions
- query reuse

Why it matters here:

This is the sort of workflow logic that makes Django feel like an application framework instead of just a request router.

### 8. Upgrade Album And Photo Management

Current state:

- Albums exist
- Photo upload exists
- Thumbnail generation is model-driven
- Album tests are basically absent

Recommended work:

- Add `PhotoForm` validation for file type, size, and dimensions
- Add batch upload with `MultiPhotoForm`
- Add `featured_photo` on `Album`
- Add `position` ordering per album
- Add `taken_at`, `camera`, `lens`, `location_name`, and `alt_text`
- Add per-photo visibility: public, unlisted, private

Implementation notes:

- Add ordering constraints scoped per album
- Use inline admin editing for fast metadata cleanup
- Move thumbnail and metadata logic into a service module if model `save()` starts getting crowded

Study guide coverage:

- `ImageField`
- model methods
- form validation
- admin inlines
- ordering
- migrations and data backfills

Why it matters here:

The albums app is the best place in this repo to practice non-trivial forms and model behavior.

### 9. Create A Public Contact Flow

Build:

- `ContactMessage` model
- Contact form with spam-resistant validation
- Admin review queue
- Optional email notification

Suggested fields:

- `name`
- `email`
- `subject`
- `message`
- `created_at`
- `status`
- `ip_address`

Study guide coverage:

- Django forms
- CSRF
- validation
- success redirects
- admin workflow

Why it matters here:

It is a classic Django feature and teaches the full request-form-save-feedback loop.

## Phase 4: Add Auth, Permissions, And User-Scoped Features

This site does not need to become a social network, but a small amount of account-aware functionality is very valuable for learning.

### 10. Add A Custom User Model Early If You Want Auth To Grow

Only do this if you expect to add any meaningful user-facing features.

Possible reasons:

- guestbook accounts
- saved reading lists
- private project notes
- photo favorites
- admin/editor distinctions

Implementation notes:

- If this is still early enough, replace the default user model before more auth-dependent work
- If not, use a profile model for now and defer a user-model migration

Study guide coverage:

- auth customization
- `OneToOneField`
- permissions

Why it matters here:

This is more about learning Django’s auth architecture than immediate product need.

### 11. Add A Guestbook Or Notes App

Build:

- Lightweight guestbook entries
- Optional moderation
- Optional logged-in posting later

Suggested fields:

- `name`
- `website`
- `message`
- `approved`
- `created_at`

Implementation notes:

- Start anonymous with moderation
- Add a honeypot field or rate-limiting later
- Moderate entries in admin first

Study guide coverage:

- forms
- moderation workflow
- admin
- list/detail patterns

Why it matters here:

It gives you a safe, small-scale way to practice user-generated content.

## Phase 5: QuerySet Practice Through Real Features

This phase is where the study guide becomes tangible. The feature ideas below are mostly valuable because they force better querying.

### 12. Build Search Across Content Types

Search:

- posts
- projects
- albums
- photos
- links or bookmarks

Implementation notes:

- Start with a simple ORM-powered search using `Q` objects and `icontains`
- Add optional weighted ranking later
- Group results by content type
- Preserve query state in pagination

Study guide coverage:

- `Q` objects
- `icontains`
- `annotate()`
- pagination

Why it matters here:

Search is one of the cleanest ways to practice dynamic query composition.

### 13. Build Site Dashboards

Possible dashboards:

- writing dashboard
- photo dashboard
- site analytics-lite dashboard

Examples:

- posts per month
- photo uploads per month
- unpublished drafts count
- albums missing descriptions
- posts missing summaries or SEO fields

Study guide coverage:

- `aggregate()`
- `annotate()`
- `Count`, `Max`, `Min`
- `values()` / `values_list()`

Why it matters here:

Dashboards teach you how to ask good questions of your data, which is one of Django ORM’s core strengths.

### 14. Add Related Content Logic

Build:

- related posts by shared tags
- more from this series
- more photos from this album
- related projects by tech stack or tags

Implementation notes:

- Start simple with shared-tag counts
- Use `annotate(shared_tags=Count("tags"))`
- Exclude the current object
- Add tests for empty and edge cases

Study guide coverage:

- aggregation
- filtering across relationships
- `distinct()`
- queryset composition

Why it matters here:

This creates the kind of useful recommendation logic Django handles very well without outside services.

## Phase 6: Introduce More Advanced Data Shapes

These are especially useful if you want broader practice than a normal personal site needs.

### 15. Add A Reading Or Bookmark App

Build:

- books
- articles
- saved links
- status tracking: queued, reading, finished, recommended

Possible models:

- `Bookmark`
- `ReadingEntry`
- `Book`
- `Author`

Good Django patterns to practice:

- many-to-many authors
- unique constraints on saved URLs
- model methods for domain-specific status helpers
- admin filters and search

Study guide coverage:

- constraints
- relationship modeling
- custom managers
- list filtering

Why it matters here:

It gives you a clean second content system that is not “just more blog posts.”

### 16. Add Comments Or Reactions

Two options:

- Full comment model with moderation
- Lightweight reactions model for likes, claps, or “helpful”

Safer recommendation:

- Start with reactions, then add comments later if wanted

Study guide coverage:

- foreign keys
- uniqueness constraints
- auth
- POST-only endpoints

Why it matters here:

It teaches write-heavy interactions without forcing a big moderation burden immediately.

### 17. Add A `Note` Or `Journal` App

Build:

- short-form posts
- dev logs
- quick ideas
- “today I learned” entries

Why this is useful:

- Lets you practice a second publishing workflow
- Good place to compare generic list/detail patterns against the main `Post` app
- Easy to expose through archive pages, feeds, or a combined timeline

Study guide coverage:

- model reuse patterns
- date archives
- small, fast CRUD flows

## Phase 7: Performance, Testing, And Maintainability

This phase is where the project becomes stronger engineering practice, not just feature accumulation.

### 18. Add Query Optimization Passes

Target areas:

- post list page
- album detail page
- future tag pages
- future project detail pages

Implementation notes:

- Use `select_related()` for single-valued relationships
- Use `prefetch_related()` for tags, photos, and reverse relations
- Consider `Prefetch()` for curated subsets like featured photos only
- Use `.exists()` and `.count()` intentionally

Study guide coverage:

- queryset laziness
- `select_related()`
- `prefetch_related()`
- `Prefetch`
- `exists()` and `count()`

Why it matters here:

As soon as this site has more relationships, performance tuning becomes a practical Django skill instead of theory.

### 19. Build Out Testing By Feature Area

Current state:

- `posts` has meaningful tests
- `albums` tests are still a placeholder

Recommended test layers:

- model tests
- form validation tests
- view permission tests
- integration tests for create/update flows
- regression tests for markdown rendering and image upload behavior

Specific priorities:

- album creation permissions
- photo upload success and failure cases
- thumbnail generation
- unpublished content visibility rules
- search and filter behavior

Study guide coverage:

- Django test client
- model and form testing
- permission testing
- regression testing

Why it matters here:

This project already has enough moving parts to benefit from a disciplined test suite.

### 20. Add Reusable Service Modules

Good candidates:

- photo thumbnailing and metadata extraction
- post publishing workflow
- search assembly
- feed generation

Implementation notes:

- Keep models slim when logic starts touching multiple concerns
- Prefer service functions over overloading views or `save()`
- Write tests around the service layer where logic is dense

Study guide coverage:

- project structure
- separation of concerns
- testability

Why it matters here:

This is how a Django project starts feeling maintainable as scope grows.

## Phase 8: Templates, Feeds, And Public-Facing Polish

These items are still good Django practice even though they are more presentation-oriented.

### 21. Add Real Archive Pages

Build:

- year archives
- month archives
- tag archives
- series archives
- project archives

Implementation notes:

- Use date-based filtering
- Reuse list templates where it actually helps
- Add archive navigation from the sidebar or header

Study guide coverage:

- URL converters
- date filtering
- list views
- context design

### 22. Add RSS/Atom/JSON Feeds

Build:

- blog feed
- notes feed
- maybe project updates feed

Study guide coverage:

- Django syndication framework
- queryset limiting
- serialization mindset

Why it matters here:

Feeds are classic personal-site features and very Django-native.

### 23. Add Sitemaps And Better SEO Metadata

Build:

- sitemap for posts, projects, albums, and core pages
- per-page meta descriptions
- canonical URLs

Study guide coverage:

- URL design
- model metadata
- site-wide context

Why it matters here:

This blends framework fundamentals with real deployment value.

## Phase 9: Admin-Heavy Low-Priority Work That Still Teaches Django

These are excellent “lower priority but high learning value” tasks.

### 24. Admin Dashboard Improvements

Build:

- custom admin filters
- readonly computed fields
- inline previews for photos
- slug prepopulation improvements
- bulk actions for publishing and featuring content

Why it is worth doing:

Admin customization is one of Django’s most distinctive strengths, and personal sites are perfect sandboxes for it.

### 25. Data Import And Export Commands

Build:

- management commands for importing markdown posts
- bulk photo metadata sync
- export content to JSON or markdown

Study guide coverage:

- custom management commands
- queryset iteration
- `bulk_create()`
- idempotent scripts

Why it matters here:

This gives hands-on practice with offline Django workflows, not just HTTP requests.

### 26. Scheduled Maintenance Jobs

Build:

- regenerate missing thumbnails
- publish scheduled posts
- backfill reading time
- mark stale drafts

Implementation notes:

- Start as management commands
- Wire them into cron or Kubernetes CronJobs later

Study guide coverage:

- `F()` expressions
- bulk updates
- management commands
- deployment operations

Why it matters here:

This is especially relevant because the repo already includes Kubernetes deployment infrastructure.

## Suggested App Map

A sensible medium-term app layout would be:

- `core`: homepage, about, now, contact, shared pages
- `posts`: long-form writing
- `albums`: photography and photo management
- `projects`: software/project portfolio and updates
- `reading`: books, bookmarks, recommendations
- `guestbook`: moderated public messages

You do not need to build all of these immediately. The main value is that each app owns a clear domain.

## Recommended Implementation Order

If the goal is steady Django learning, this is a strong order:

1. Namespace existing URLs and clean up route ownership.
2. Add `core` for static and semi-static pages.
3. Expand `Post` with status, summary, and publishing workflow.
4. Add tags and series.
5. Build `Project` as a second major content app.
6. Strengthen `albums` with validation, metadata, ordering, and tests.
7. Add contact flow and admin moderation patterns.
8. Add search and dashboards for queryset practice.
9. Add reading/bookmark or guestbook features.
10. Add feeds, sitemap, management commands, and scheduled maintenance.

## Strong First Milestone

If you want one milestone that teaches a lot of Django without exploding scope, make it this:

- Create `core`
- Add URL namespacing
- Refactor `Post` to use `status`
- Add `Tag` and `Series`
- Create `Project`
- Fill in `albums` tests

That one milestone touches:

- app design
- models
- migrations
- forms
- admin
- URLs
- CBVs
- testing
- query optimization

## Optional Stretch Ideas

These go beyond what a personal site strictly needs, but they are excellent Django practice:

- public API endpoints for posts/projects/photos
- HTMX-enhanced uploads or previews
- private dashboard with per-object notes
- per-project changelogs
- email newsletter signup model and admin review
- unified activity timeline combining posts, notes, and project updates
- generated “best of” pages from query annotations

## Final Recommendation

Treat this project less like “my blog” and more like “my personal Django lab that also happens to be my website.”

That mindset makes lower-priority work worth doing, because even small features can teach a core concept well:

- a guestbook teaches moderation and forms
- a reading list teaches relationships and admin
- scheduled publishing teaches state transitions and commands
- project pages teach richer models and templates
- search teaches query composition
- dashboards teach aggregation

If you keep choosing features that force you to touch one or two new Django concepts at a time, this codebase can absolutely become a strong path through the study guide.
