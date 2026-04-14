# s8njee-web

Single Django site — blog at `/`, photo gallery at `/photos/`.

Application code lives in `blog/`. The old standalone `photos/` service is archived under `archive/photos-standalone-app/`.

---

## Quick start

```bash
cp blog/.env.example blog/.env   # fill in values; leave DB_* blank for SQLite
cd blog && uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

See [docs/Engineering.md](docs/Engineering.md) for full local dev, deployment, backup, and Kubernetes details.

---

## Configuration files

Every file listed here is a place where you directly change behaviour. The role column describes where Django (or the container runtime) picks it up.

### Runtime environment

| File | Role in Django |
|------|----------------|
| `blog/.env` | Loaded by `settings/base.py` via `python-dotenv` at startup. Every `env('VAR')` call in settings reads from here. This is the primary knob file for secrets and mode switches. |
| `blog/.env.example` | Template — documents every variable `base.py` reads. Copy to `.env` and fill in. |
| `db.env.example` | Documents the three PostgreSQL variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) that the cluster's PostgreSQL StatefulSet reads via `envFrom`. Copy to `db.env` for Docker Compose use. |

#### Variables in `blog/.env`

| Variable | Default | Effect |
|----------|---------|--------|
| `SECRET_KEY` | insecure dev value | Django's cryptographic signing key. **Must be set in production.** |
| `DJANGO_SETTINGS_MODULE` | — | Which settings module to load. Set to `blog.settings.production` in the container; defaults to `blog.settings.development` for `runserver`. |
| `DEBUG` | `True` in dev settings | Enables Django debug pages. Always `False` in `settings/production.py`. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list. Django rejects requests with a `Host` header not in this list. |
| `CSRF_TRUSTED_ORIGINS` | — | Comma-separated origins for CSRF. Required in production when the app is behind a reverse proxy. |
| `ENABLE_SSL` | `False` | Enables `SECURE_SSL_REDIRECT`, `HSTS`, and secure cookies in `settings/production.py`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | blank → SQLite | Blank values leave Django on SQLite. Set all five to switch to PostgreSQL. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | blank | S3 credentials. Leave blank to store uploads on the local filesystem. |
| `AWS_STORAGE_BUCKET_NAME` | blank | Presence of this variable switches Django's default storage backend from `FileSystemStorage` to `S3Boto3Storage`. |
| `AWS_S3_REGION_NAME` | `us-east-1` | S3 region for the bucket above. |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis URL for the Celery task queue used by async photo processing. |
| `CELERY_TASK_ALWAYS_EAGER` | `True` in dev, `False` in prod | When `True`, Celery tasks run synchronously in-process — no worker or Redis needed locally. |

---

### Django settings modules

| File | Role |
|------|------|
| `blog/blog/settings/base.py` | Shared settings loaded by both dev and prod. Defines `INSTALLED_APPS`, `MIDDLEWARE`, `TEMPLATES`, `STORAGES`, Celery config, and upload size limits. Edit here for app-wide changes. |
| `blog/blog/settings/development.py` | Dev overrides: `DEBUG=True`, SQLite database, `CELERY_TASK_ALWAYS_EAGER=True`. |
| `blog/blog/settings/production.py` | Production overrides: `DEBUG=False`, PostgreSQL, SSL/HSTS switches, enforced `SECRET_KEY` check. |

---

### URL and application wiring

| File | Role |
|------|------|
| `blog/blog/urls.py` | Root URLconf — mounts `posts.urls` at `/`, `albums.urls` at `/photos/`, registers the sitemap, robots.txt, RSS feed, and custom error handlers (`handler404`, `handler500`). |
| `blog/posts/urls.py` | URL patterns for the blog: post list, post detail, month archive, post editor, image upload, preview API. |
| `blog/albums/urls.py` | URL patterns for the photo gallery: album list/create/edit/delete, photo upload/edit/delete/reorder, lightbox permalink, cover photo. |

---

### Celery

| File | Role |
|------|------|
| `blog/blog/celery.py` | Celery app entry point. Sets `DJANGO_SETTINGS_MODULE` to `blog.settings.production` and reads all `CELERY_*` settings from Django's settings namespace. |
| `blog/albums/tasks.py` | Defines `process_photo` — the async task that converts RAW/HEIC → AVIF, generates image variants (1920px / 1200px / 800px), extracts EXIF, and saves thumbnails. |

---

### Static and media files

| File / Setting | Role |
|----------------|------|
| `blog/static/css/style.css` | Single shared stylesheet for the entire site. |
| `STATIC_ROOT` (`blog/staticfiles/`) | Where `collectstatic` writes output files. Served by WhiteNoise. |
| `MEDIA_ROOT` (`blog/media/`) | Where Django writes uploaded files when S3 is not configured. Not served in production — use S3. |
| `blog/blog/settings/base.py` → `STORAGES` | Controls which storage backend is active. Switches automatically based on whether `AWS_STORAGE_BUCKET_NAME` is set. |

---

### Container and deployment

| File | Role |
|------|------|
| `blog/Dockerfile` | Builds the application image. Installs Python deps with `uv`, copies app code, sets `start.sh` as the entrypoint. Rebuild when `pyproject.toml`, `uv.lock`, or system-level deps change. |
| `blog/start.sh` | Production startup script. Runs `migrate`, seeds the DB if empty, runs `collectstatic`, then starts Uvicorn. Changing the startup sequence (e.g. adding a backfill command) means editing this file. |
| `blog/pyproject.toml` | Python package dependencies. Add or remove packages here; `uv sync` regenerates `uv.lock`. |
| `blog/uv.lock` | Locked dependency graph. Commit this. Do not edit by hand. |

---

### Kubernetes manifests

| Path | Role |
|------|------|
| `k8s/base/deployment.yaml` | Base Deployment — image, resource limits, env references, readiness probe. |
| `k8s/base/service.yaml` | Base Service definition. |
| `k8s/base/kustomization.yaml` | Base Kustomize root — lists all base resources. |
| `k8s/base/postgres-backup-cronjob.yaml` | CronJob for scheduled PostgreSQL backups. |
| `k8s/overlays/netcup/` | Netcup-specific patches: image tag, replica count, ingress hostname, Sealed Secret refs. |
| `k8s/overlays/freya/` | Freya-specific patches: local registry image, dev resource limits. |
| `k8s/argocd/` | Argo CD `Application` manifests that point each overlay at a cluster. |

---

### Documentation index

| File | Contents |
|------|----------|
| [docs/Engineering.md](docs/Engineering.md) | Local dev, Kubernetes deployment, Argo CD, Freya sync, backup/restore, seed data |
| [DEPLOY.md](DEPLOY.md) | Step-by-step deployment runbook and migration staging workflow |
| [k8s/README.md](k8s/README.md) | Manifest layout and Argo CD details |
| [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md) | Release checklist |
| [docs/EDITORIAL.md](docs/EDITORIAL.md) | How to write, publish, and manage posts and albums |
| [docs/ToDo.md](docs/ToDo.md) | Active backlog |
