# Netcup Deployment Guide

Netcup is the public production cluster. It serves `https://blog.s8njee.com`.

See `DEPLOY.md` at the repo root for the full reference. This document covers the
pre-flight checklist and the steps specific to a Netcup release.

---

## Pre-flight Checklist

### 1. Secrets

Confirm `k8s/overlays/netcup/sealed-secret.yaml` contains up-to-date sealed values for:

- `SECRET_KEY`
- `DB_USER`, `DB_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`

If rotating credentials, reseal with `kubeseal` and commit before deploying.

### 2. Staged Migrations

Any new Django migrations must be copied to `deploy/netcup/migrations/<app>/` before the release.

Currently staged:

| App    | Migration                                      |
|--------|------------------------------------------------|
| albums | `0005_alter_photo_options_photo_sort_order.py` |
| albums | `0006_album_cover_photo.py`                    |
| albums | `0007_photo_image_variants.py`                 |
| albums | `0008_album_slug_photo_alt_text.py`            |
| posts  | `0002_post_published_at.py`                    |

These will be applied automatically by `start.sh` on pod startup. After a successful
rollout, verify the pod logs show the migrations applied, then clear the staged copies.

### 3. Argo CD Image Updater

`k8s/argocd/image-updater.yaml` must list both the web deployment and the Celery worker
so new image pushes roll both. Confirm it contains two entries under `images:`:

```yaml
- alias: s8njee-web
  imageName: registry.s8njee.com/s8njee-web:<tag>
  manifestTargets:
    kustomize:
      name: s8njee-web
- alias: s8njee-celery-worker
  imageName: registry.s8njee.com/s8njee-web:<tag>
  manifestTargets:
    kustomize:
      name: s8njee-celery-worker
```

If the `ImageUpdater` resource is already applied to the cluster, re-apply after any change:

```bash
kubectl --context=netcup apply -n argocd -f k8s/argocd/image-updater.yaml
```

### 4. New Resources This Release

The following resources are being added to the netcup overlay for the first time:

- `k8s/overlays/netcup/valkey-deployment.yaml` — Valkey broker (Redis-compatible)
- `k8s/overlays/netcup/valkey-service.yaml` — ClusterIP service for Valkey
- `k8s/overlays/netcup/celery-worker-deployment.yaml` — Celery worker for async photo processing

The `CELERY_BROKER_URL` / `REDIS_URL` is already set in `configmap.yaml` as
`redis://valkey:6379/1`. No secret changes are needed.

---

## Deploy Steps

### Build and Push the Image

```bash
TAG="sha-$(git rev-parse --short HEAD)"
docker buildx build --platform linux/amd64 --push \
  -t "registry.s8njee.com/s8njee-web:${TAG}" \
  ./blog
```

Argo CD Image Updater will detect the new tag and roll the deployment automatically.

### First-Time Apply (if Argo CD is not yet syncing)

```bash
kubectl --context=netcup apply -k k8s/overlays/netcup
```

### Verify the Rollout

```bash
# All pods
kubectl --context=netcup get pods -n s8njee-web

# Rollout status
kubectl --context=netcup rollout status deploy/s8njee-web -n s8njee-web
kubectl --context=netcup rollout status deploy/s8njee-celery-worker -n s8njee-web
kubectl --context=netcup rollout status statefulset/s8njee-postgres -n s8njee-web

# Confirm migrations ran
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-web --tail=200

# Confirm Celery worker connected to Valkey
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-celery-worker --tail=100
```

### Smoke Check

```bash
curl -I https://blog.s8njee.com/
curl -I https://blog.s8njee.com/photos/
```

- Log into `/admin/` and confirm posts and albums are accessible.
- Upload a test image and confirm it processes to AVIF and lands in S3.

---

## Post-Deploy Cleanup

Once the rollout is confirmed healthy:

1. Clear staged migrations from `deploy/netcup/migrations/`.
2. Update `docs/DEPLOYMENT_CHECKLIST.md` migration table.
3. Update `DEPLOY.md` staged migration list.

---

## Celery Worker Notes

The Celery worker processes photo uploads asynchronously (AVIF conversion, variant
generation, thumbnail creation). It runs with `--concurrency=4` on netcup's 4-CPU VPS.

If the photo upload queue appears stuck:

```bash
# Check worker logs
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-celery-worker --tail=100

# Check Valkey is reachable
kubectl --context=netcup exec -n s8njee-web deploy/s8njee-celery-worker -- \
  sh -c 'uv run python -c "import redis; r=redis.from_url(\"redis://valkey:6379/1\"); print(r.ping())"'
```

## Manual Migration (if needed)

```bash
kubectl --context=netcup exec -n s8njee-web deploy/s8njee-web -- \
  sh -c 'DJANGO_SETTINGS_MODULE=blog.settings.production \
    DB_HOST="${S8NJEE_POSTGRES_SERVICE_HOST:-${DB_HOST:-}}" \
    uv run python manage.py migrate --noinput'
```
