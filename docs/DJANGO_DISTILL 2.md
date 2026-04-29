# `django-distill` as a Cold-Standby Fallback

Using `django-distill` to maintain a static export of the public site on
Cloudflare Pages, automatically served when the netcup backend is unreachable.
The primary site stays fully dynamic; the static build is insurance.

This is scoped as a **read-only failover**, not a replacement. Publishing, the
editor, and admin stay on netcup.

---

## Mental Model

```
        Normal                               Outage
┌──────────────────────┐             ┌──────────────────────┐
│   netcup (primary)   │     ←→      │  Cloudflare Pages    │
│   Django + Postgres  │   fallback  │  Static HTML         │
│   Celery + Valkey    │     ←────   │  + R2 for photos     │
└──────────────────────┘             └──────────────────────┘
          ↑                                      ↑
          │              Router                  │
          └────────────  (Worker)  ───────────────┘
                            ↑
                        Visitor
```

A Cloudflare Worker sits in front of both origins. It tries netcup first.
On 5xx/timeout, it serves the latest static export from Pages. Visitors see a
slightly stale but functional site while you fix the primary.

---

## What Survives a Static Build, What Doesn't

### Survives (distillable GET views)

From [blog/blog/urls.py](blog/blog/urls.py) and app-level URL configs:

| URL pattern                         | View                      | Notes                 |
| ----------------------------------- | ------------------------- | --------------------- |
| `/`                                 | `PostListView`            | Single URL            |
| `/<slug>/`                          | `PostDetailView`          | Iterate published posts |
| `/archive/<year>/<month>/`          | `PostMonthArchiveView`    | Iterate months with posts |
| `/photos/`                          | `AlbumListView`           | Single URL            |
| `/photos/s/<slug>/`                 | `album_detail` (by slug)  | Iterate public albums |
| `/photos/<album_pk>/photos/<photo_pk>/` | `photo_permalink`      | Iterate (album, photo) pairs |
| `/feed/`                            | `LatestPostsFeed`         | Single URL            |
| `/sitemap.xml`                      | `sitemap`                 | Single URL            |
| `/robots.txt`                       | `TemplateView`            | Single URL            |

### Does Not Survive (and is fine during outage)

| URL                                 | Why it breaks             | Mitigation              |
| ----------------------------------- | ------------------------- | ----------------------- |
| `/admin/*`                          | Form POSTs, auth          | Expected — no publishing during outage |
| `/editor/*`                         | POSTs, CSRF               | Hide nav link when `DISTILL_BUILD=1` |
| `/login/`, `/accounts/*`            | Auth                      | Same                    |
| `/photos/<uuid>/` (UUID variant)    | Private, UUID only        | Don't distill — rely on slug URL |
| Photo upload / edit / reorder       | All POSTs                 | Same                    |

Photos themselves keep working in fallback because they're served from R2 via
an absolute URL — the static HTML just references them.

---

## Implementation

### 1. Install

```bash
cd blog
uv add django-distill
```

Add to `INSTALLED_APPS` in [blog/blog/settings/base.py](blog/blog/settings/base.py):

```python
INSTALLED_APPS = [
    # ...
    "django_distill",
]
```

### 2. Register Distill URLs

`django-distill` doesn't auto-discover — each URL must be declared distillable.
Replace `path()` with `distill_path()` for public views and supply a generator
for parametric URLs.

Example for [blog/posts/urls.py](blog/posts/urls.py):

```python
from django_distill import distill_path
from posts.models import Post

def published_post_slugs():
    return Post.objects.filter(status="published").values_list("slug", flat=True)

def published_archive_months():
    return (
        Post.objects.filter(status="published")
        .dates("published_at", "month")
        .values_list("published_at__year", "published_at__month")
    )

urlpatterns = [
    # Editor routes stay as regular path() — not distilled.
    path("editor/posts/new/", views.PostEditorView.as_view(), name="post_editor_new"),
    # ... other editor paths ...

    distill_path("", views.PostListView.as_view(), name="post_list"),
    distill_path(
        "archive/<int:year>/<int:month>/",
        views.PostMonthArchiveView.as_view(),
        name="post_archive_month",
        distill_func=published_archive_months,
    ),
    distill_path(
        "<slug:slug>/",
        views.PostDetailView.as_view(),
        name="post_detail",
        distill_func=published_post_slugs,
    ),
]
```

Mirror the same pattern in [blog/albums/urls.py](blog/albums/urls.py) for
`album_list`, `album_detail_slug`, and `photo_permalink`. Skip all editor/upload
routes — they stay as regular `path()`.

For `/sitemap.xml`, `/feed/`, `/robots.txt` in [blog/blog/urls.py](blog/blog/urls.py),
swap to `distill_path` with no `distill_func` (they're single URLs).

### 3. Build Flag to Hide Dynamic UI

Add to settings:

```python
DISTILL_BUILD = env_bool("DISTILL_BUILD", False)
```

Use a context processor or template tag so templates can do:

```django
{% if not distill_build %}
  <a href="{% url 'post_editor_new' %}">New post</a>
{% endif %}
```

This keeps the static export clean of dead links.

### 4. Management Command Wrapper

Distill exposes `manage.py distill-local <dir> --force`. Wrap it in a project
command so the CI job is one line:

```python
# blog/posts/management/commands/build_static_fallback.py
from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = "Build the static-fallback export for Cloudflare Pages."

    def handle(self, *args, **opts):
        call_command("distill-local", "build/", force=True, quiet=False)
        self.stdout.write(self.style.SUCCESS("Static export written to build/"))
```

### 5. CI Job

GitHub Actions workflow, triggered nightly + on deploy + manual:

```yaml
# .github/workflows/static-fallback.yml
name: Build static fallback
on:
  schedule: [{ cron: "17 4 * * *" }]  # 04:17 UTC daily
  workflow_dispatch: {}
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      DATABASE_URL: ${{ secrets.READONLY_DATABASE_URL }}
      DISTILL_BUILD: "1"
      DJANGO_SETTINGS_MODULE: blog.settings.prod
      # R2 credentials so MEDIA_URL resolves during build
      AWS_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
      AWS_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
      AWS_STORAGE_BUCKET_NAME: ${{ secrets.R2_BUCKET }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
        working-directory: blog
      - run: uv run python manage.py build_static_fallback
        working-directory: blog
      - uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: pages deploy blog/build --project-name=s8njee-fallback
```

Use a **read-only** Postgres role (`READONLY_DATABASE_URL`) so a runaway build
job can't corrupt production data.

### 6. Fallback Routing (the Router Worker)

Three options, ranked by recommendation:

**A. Cloudflare Worker in front of both origins (recommended, ~$0).**

```js
// workers/router.js
const PRIMARY = "https://s8njee.com";          // netcup ingress
const FALLBACK = "https://s8njee-fallback.pages.dev";

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    try {
      const upstream = new URL(url.pathname + url.search, PRIMARY);
      const res = await fetch(upstream, {
        cf: { fetchTimeout: 5000 },
        redirect: "manual",
      });
      if (res.status >= 500) throw new Error(`primary ${res.status}`);
      return res;
    } catch {
      const fallback = new URL(url.pathname + url.search, FALLBACK);
      const res = await fetch(fallback);
      // Add a header so you can tell from curl if you're on the standby.
      const h = new Headers(res.headers);
      h.set("x-served-by", "fallback");
      return new Response(res.body, { status: res.status, headers: h });
    }
  },
};
```

Free Workers plan (100k req/day) covers a hobby site. Paid at $5/month if you
outgrow it.

**B. Cloudflare Load Balancer with health checks ($5/mo + $0.50/origin).**
Zero-code, GUI-configured, automatic health checks. Cleanest operationally, but
you're already paying for Workers Paid once you have one use case.

**C. Manual DNS swap.** Keep `s8njee-fallback.pages.dev` as a named alternate.
When netcup dies, update the CNAME in Cloudflare DNS. Free, but requires you
to be awake and near a laptop. Fine for a personal site if outages are rare.

---

## Operational Concerns

*   **Freshness:** the fallback is as old as the last build. Nightly + on-deploy
    is plenty for an archival site. Post-publish hook could trigger an extra
    build, but probably overkill.
*   **Absolute URLs:** distill renders using `reverse()`, so keep `ALLOWED_HOSTS`
    and `SITE_URL` correct during build (use `localhost` or the real domain;
    don't mix). Check that your RSS feed and sitemap generate absolute URLs —
    they need the real public hostname.
*   **Forms on static pages:** even with the build flag, some templates may
    include inline forms (search, newsletter). Either hide them behind
    `{% if not distill_build %}` or add a banner on the fallback Page explaining
    reduced functionality.
*   **404s during fallback:** any URL not in the distilled set returns 404 from
    Pages. That includes `/admin/`, which is correct — don't want admin
    surface exposed during outage.
*   **Photo URLs:** they're already on R2. Nothing to do. This is why R2 pairs
    so well with this pattern — media keeps working regardless of which origin
    is live.
*   **Search (if adopted):** the Postgres full-text search in `IDEAS.md` would
    not work on fallback. A minimal alternative is to build a client-side
    index (lunr.js / pagefind) at distill time, but this is extra scope — skip
    unless search is critical during outages.

---

## Testing the Fallback

Regular drill, so you find out it's broken *before* you need it:

1.  Deploy the Worker router to a staging subdomain.
2.  Manually block the primary (`iptables` rule on the netcup side, or point
    `PRIMARY` to an invalid host).
3.  Load the site through the Worker. Confirm `x-served-by: fallback` header
    and that pages render.
4.  Restore.

Add this as a quarterly calendar reminder. A fallback you've never tested is a
fallback you don't have.

---

## When NOT to Do This

*   **Before R2 migration.** If photos are still on netcup-local storage, the
    fallback renders HTML with broken image links. Move media to R2 first
    (see [CLOUDFLARE.md](CLOUDFLARE.md) Tier 1).
*   **If the site has many filter permutations.** django-distill enumerates
    URLs; combinatorial filter pages blow up the build. The current URL map
    is safe, but be cautious if you add the `django-filter` EXIF archive in
    `IDEAS.md` — distill only the landing page, not every filter combination.
*   **If uptime matters enough to pay for it.** A second always-on origin on
    Hetzner (€3.79/month) is simpler than orchestrating a static standby, and
    covers DB-dependent features too. The distill approach only wins on cost
    and on pairing naturally with Cloudflare Pages.

---

## Rough Cost

| Item                                 | Cost           |
| ------------------------------------ | -------------- |
| Cloudflare Pages (fallback hosting)  | Free           |
| R2 (photos — already planned)        | ~$0.75/month   |
| Worker router (free tier)            | $0 up to 100k req/day |
| GitHub Actions nightly build         | Free (public repo) |
| **Total marginal cost**              | **~$0–$5/mo**  |

Cheaper than any second VM, at the cost of accepting a read-only site during
outages.
