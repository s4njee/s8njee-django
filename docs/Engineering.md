# Engineering Guide

Operational details for local development, deployment, and infrastructure.

---

## Prerequisites

- Python 3.13 and `uv` for local development
- Docker for building container images
- A Kubernetes cluster with Argo CD for deployment

---

## Local Development

The local development path is the Django app in `blog/` with SQLite by default.

1. Copy `blog/.env.example` to `blog/.env`.
2. Leave the `DB_*` variables blank to use SQLite, or point them at a running PostgreSQL instance.
3. Start the app:

```bash
cd blog
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The site is at [http://127.0.0.1:8000/](http://127.0.0.1:8000/) with photos at [http://127.0.0.1:8000/photos/](http://127.0.0.1:8000/photos/).

Celery tasks run synchronously in development (`CELERY_TASK_ALWAYS_EAGER=True` in `settings/development.py`), so there is no need to run a worker or Redis locally.

There is no Webpack/Tailwind build step. All CSS is in `blog/static/css/style.css`.

### Generating a secret key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## Startup Paths

| Mode | Command |
|------|---------|
| Local dev | `cd blog && uv sync && uv run python manage.py migrate && uv run python manage.py runserver` |
| Production | Container boot runs `blog/start.sh` — runs migrations, seeds an empty DB, collects static, starts Uvicorn |

---

## Kubernetes Deployment

Production deployment is Kubernetes-first and uses:

- Kustomize manifests in `k8s/base` and `k8s/overlays/*`
- Argo CD `Application` manifests in `k8s/argocd`
- Bitnami Sealed Secrets for encrypted secret material
- A persistent PostgreSQL PVC on `freya` named `s8njee-postgres-data`

### Argo CD access

The Argo CD UI is at `https://argo.s8njee.com`.

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

argocd login argo.s8njee.com \
  --grpc-web \
  --username admin \
  --password "$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
```

### Deploying to Netcup (primary)

```bash
git push origin main
```

Argo CD reconciles the Kubernetes manifests from Git. Netcup image rollouts are handled by Argo CD Image Updater — the workflow only builds and pushes a new image tag; it does not commit deploy updates back to `main`.

### Deploying to Freya (dev cluster)

Freya is optimised for quick iteration: source files are synced directly without rebuilding the image for every Django/template/static change.

```bash
scripts/freya-sync.sh
```

Freya still uses a base image from `192.168.1.248:5001`. Image rebuilds are only needed when `blog/Dockerfile`, `blog/pyproject.toml`, or `blog/uv.lock` changes.

**Do not delete or rename the PostgreSQL PVC `s8njee-postgres-data-freya`** unless you are intentionally replacing the Freya database.

### Runtime checks

```bash
kubectl --context=freya get application s8njee-web-freya -n argocd
kubectl --context=freya get deploy,pods,svc,pvc,sealedsecret,secret -n default | rg 's8njee'
kubectl --context=freya rollout status deploy/s8njee-web -n default
```

```bash
kubectl logs -n s8njee-web deploy/s8njee-web --tail=200
curl -I https://blog.s8njee.com
curl -I https://argo.s8njee.com
```

See also [../k8s/README.md](../k8s/README.md) for manifest layout and Argo CD details, and [../DEPLOY.md](../DEPLOY.md) for the step-by-step deployment runbook.

---

## Storage Modes

| Mode | Trigger | Media location |
|------|---------|----------------|
| Local filesystem | `AWS_STORAGE_BUCKET_NAME` not set | `blog/media/` |
| S3 | `AWS_STORAGE_BUCKET_NAME` set | S3 bucket root |

Static files are always collected during container startup via `manage.py collectstatic` and served by WhiteNoise.

If you switch between modes, keep `MEDIA_ROOT`, `MEDIA_URL`, and the S3 bucket name consistent with the deployment target.

---

## Backup And Restore

### PostgreSQL

Create a logical backup from the running cluster:

```bash
kubectl exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  > backups/s8njee-current.sql
```

Restore into the dedicated blog database:

```bash
kubectl exec -i -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backups/s8njee-current.sql
```

For a clean overwrite, drop and recreate the `public` schema before restoring, then rerun `manage.py migrate` if needed.

### Media (S3)

```bash
aws s3 sync s3://s8njee-photoblog/media/ backups/media/
aws s3 sync backups/media/ s3://s8njee-photoblog/media/
```

---

## Seed Data

Fresh empty deployments are seeded from [`blog/fixtures/seed_content.json`](../blog/fixtures/seed_content.json).

The fixture contains live content for `posts.post`, `albums.album`, and `albums.photo`. Photo rows reference S3 object keys only — to render images on a seeded environment, point the app at the same S3 bucket or restore the matching media files separately.

Seeding only runs when the database is empty (`start.sh` checks row count before loading).

---

## Deployment Checklist

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for the full release checklist.
