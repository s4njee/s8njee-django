# Engineering Guide

Operational details for local development, deployment, and infrastructure.

---

## Prerequisites

- Python 3.13 and `uv` for local development
- Docker for building container images
- `kubectl` with contexts configured for `netcup` and `freya`
- Argo CD CLI (`argocd`) for deployment management

---

## Local Development

The app lives in `blog/`. SQLite is the default database for local dev — no Postgres needed.

1. Copy `blog/.env.example` to `blog/.env` and fill in values. Leave `DB_*` blank to use SQLite.
2. Run:

```bash
cd blog
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The site is at [http://127.0.0.1:8000/](http://127.0.0.1:8000/) with photos at [http://127.0.0.1:8000/photos/](http://127.0.0.1:8000/photos/).

Celery tasks run synchronously in development (`CELERY_TASK_ALWAYS_EAGER=True` in `settings/development.py`), so no Redis or worker process is needed locally.

There is no build step for CSS or JS. All styles are in `blog/static/css/style.css`.

### Generating a secret key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## Startup Paths

| Mode | What runs |
|------|-----------|
| Local dev | `uv run python manage.py migrate && uv run python manage.py runserver` |
| Production container | `blog/start.sh` — migrate → seed if empty → backfills → collectstatic → Uvicorn |

`start.sh` is the canonical production entrypoint. It runs these steps in order every time the container starts:

1. `manage.py migrate --noinput`
2. Load `fixtures/seed_content.json` only if the DB has no posts or albums
3. `manage.py backfill_photo_sort_order`
4. `manage.py backfill_album_slugs`
5. `manage.py backfill_image_variants`
6. `manage.py collectstatic --noinput`
7. Start Uvicorn on port 8000

---

## Kubernetes Deployment

Production runs on Kubernetes. There are two clusters:

| Cluster | Context | Namespace | Purpose |
|---------|---------|-----------|---------|
| Netcup | `netcup` | `s8njee-web` | Public production — `https://blog.s8njee.com` |
| Freya | `freya` | `default` | Local dev/staging — `http://192.168.1.248:4201` |

Manifests live in `k8s/base` (shared) and `k8s/overlays/<cluster>` (per-cluster patches). Argo CD `Application` manifests are in `k8s/argocd/`.

### Deploying to Netcup

```bash
git push origin main
```

Argo CD watches the repo and reconciles `k8s/overlays/netcup` automatically. Image rollouts are handled by Argo CD Image Updater — push a new image tag and it updates the live deployment without a Git commit.

### Deploying to Freya

Freya is optimised for fast iteration. Source files are rsynced directly to the node; the running container picks them up via `hostPath` mounts and Uvicorn's `--reload`.

```bash
scripts/freya-sync.sh           # sync source files only
scripts/freya-sync.sh --rollout # sync + restart the web pod
```

Only rebuild the Freya image when `blog/Dockerfile`, `blog/pyproject.toml`, or `blog/uv.lock` changes.

**Do not delete or rename the PVC `s8njee-postgres-data-freya`** unless you are intentionally replacing the Freya database.

### Argo CD access

The Argo CD UI is at `https://argo.s8njee.com`.

```bash
# Get the initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

# Log in with the CLI
argocd login argo.s8njee.com \
  --grpc-web \
  --username admin \
  --password "$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
```

### Runtime checks

Netcup:
```bash
kubectl --context=netcup get deploy,pods,svc,pvc -n s8njee-web
kubectl --context=netcup rollout status deploy/s8njee-web -n s8njee-web
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-web --tail=200
```

Freya:
```bash
kubectl --context=freya get deploy,pods,svc,pvc -n default | grep s8njee
kubectl --context=freya rollout status deploy/s8njee-web -n default
kubectl --context=freya logs -n default deploy/s8njee-web --tail=200
```

---

## Storage

The app supports two media storage backends, selected by environment variable:

| Mode | Trigger | Where uploads go |
|------|---------|-----------------|
| Local filesystem | `AWS_STORAGE_BUCKET_NAME` not set | `blog/media/` |
| S3-compatible | `AWS_STORAGE_BUCKET_NAME` set | S3/B2 bucket |

Static files are always served by WhiteNoise (collected at container startup via `collectstatic`).

**Note:** Production is migrating from AWS S3 to Backblaze B2. The `AWS_*` env vars are reused for B2 credentials since `django-storages` supports B2 via the S3-compatible API. See the Backblaze migration section below.

---

## Backup and Restore

### Mirror netcup DB to freya

```bash
scripts/netcup-to-freya-db-sync.sh
```

This dumps netcup (read-only), wipes freya's DB, restores the dump, and bounces the freya web pod.

### Manual PostgreSQL dump

Netcup (StatefulSet pod):
```bash
kubectl --context=netcup exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip > backups/netcup-$(date +%Y%m%d-%H%M%S).sql.gz
```

Freya (Deployment pod — name varies):
```bash
kubectl --context=freya exec -n default \
  "$(kubectl --context=freya get pod -n default -l app=s8njee-postgres -o jsonpath='{.items[0].metadata.name}')" -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip > backups/freya-$(date +%Y%m%d-%H%M%S).sql.gz
```

### Restore a dump

For a clean overwrite, drop and recreate the `public` schema first:

```bash
# Drop schema (replace context/namespace/pod as needed)
kubectl --context=netcup exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'

# Restore
gunzip -c backups/<file>.sql.gz | \
  kubectl --context=netcup exec -i -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q'
```

### Media backup

```bash
# Download from bucket
aws s3 sync s3://s8njee-photoblog/ backups/s8njee-photoblog/

# Upload to bucket
aws s3 sync backups/s8njee-photoblog/ s3://s8njee-photoblog/
```

---

## Wiping Photo Albums (Backblaze Migration)

When migrating photo storage to Backblaze, albums and photos are wiped from the DB so they can be re-uploaded with correct EXIF data against the new storage backend.

**Status:** Done on freya (2026-04-15) as a dry run. Pending on netcup until photos are re-uploaded.

### Wipe command

```bash
# Freya
kubectl --context=freya exec -n default \
  "$(kubectl --context=freya get pod -n default -l app=s8njee-postgres -o jsonpath='{.items[0].metadata.name}')" -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "TRUNCATE albums_photo, albums_album RESTART IDENTITY CASCADE;"'

# Netcup (StatefulSet pod name is fixed)
kubectl --context=netcup exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "TRUNCATE albums_photo, albums_album RESTART IDENTITY CASCADE;"'
```

### Order of operations for netcup

1. Update the netcup Sealed Secret with Backblaze B2 credentials (`AWS_*` vars pointing at the B2 bucket and endpoint).
2. Re-upload all photo albums through the UI so EXIF is extracted fresh against B2.
3. Run the TRUNCATE above against netcup once satisfied with the new uploads.
4. Decommission the old S3 bucket after confirming all media is in B2.

---

## Seed Data

Fresh empty deployments are seeded from `blog/fixtures/seed_content.json`.

The fixture contains blog posts, albums, and photos from the production site. Photo rows reference storage object keys — to render images on a seeded environment, point the app at the same storage bucket.

Seeding only runs when the database is empty (`start.sh` checks for existing posts or albums before loading).

---

## Deployment Checklist

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for the release checklist.
