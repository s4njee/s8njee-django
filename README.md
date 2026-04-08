# s8njee-web

Single Django site for the blog and photo gallery.

- Blog lives at `/`
- Photos live at `/photos/`
- Active application code lives in `blog/`
- The old standalone `photos/` service has been archived under `archive/photos-standalone-app/`

## Prerequisites

- Python 3.13 and `uv` for local development
- Docker for building container images
- A Kubernetes cluster with Argo CD for deployment

## Environment Files

Copy the example files and fill in real values for local development:

```bash
cp .env.example .env
cp blog/.env.example blog/.env
cp db.env.example db.env
```

- `blog/.env` configures Django.
- `db.env` configures PostgreSQL.
- `.env` is legacy host-level config and is not used by the current Kubernetes deployment flow.

Generate a Django secret key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

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

The site will be available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/) with photos under [http://127.0.0.1:8000/photos/](http://127.0.0.1:8000/photos/).

## Startup Paths

There are two supported startup paths:

- Local development: `cd blog && uv sync && uv run python manage.py migrate && uv run python manage.py runserver`
- Production: container boot runs [`blog/start.sh`](/Users/sanjee/Documents/projects/s8njee-web/blog/start.sh), which runs migrations, seeds only on an empty database, collects static files, and starts Uvicorn

There is no separate Webpack/Tailwind build step.

## Kubernetes Deployment

Production deployment is Kubernetes-first and uses:

- Kustomize manifests in `k8s/base` and `k8s/overlays/*`
- Argo CD `Application` manifests in `k8s/argocd`
- Bitnami Sealed Secrets for encrypted secret material
- a persistent PostgreSQL PVC on `mars` named `s8njee-postgres-data`

### Argo CD Access

The Argo CD UI is exposed at `https://argo.s8njee.com`.

Install the CLI, then log in with the initial admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo

argocd login argo.s8njee.com \
  --grpc-web \
  --username admin \
  --password "$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
```

If you rotate the Argo CD admin password later, keep using the same `argocd login` command and replace the password source.

The app container still uses `blog/start.sh` as the release entrypoint. On startup it runs migrations, loads starter content only on an empty database, collects static files, and then starts Uvicorn.

## Deploying To Mars

The current `mars` cluster is synced by Argo CD from [s8njee-django](https://github.com/s4njee/s8njee-django).

1. Build and push a new image.
2. Update the image tag in [`k8s/overlays/mars/kustomization.yaml`](/Users/sanjee/Documents/projects/s8njee-web/k8s/overlays/mars/kustomization.yaml).
3. Commit and push to `main`.
4. Let Argo CD sync `s8njee-web-mars`.

Important: do not delete or rename the PostgreSQL PVC `s8njee-postgres-data` unless you are intentionally replacing the database.

Detailed deployment guidance lives in:

- [DEPLOY.md](/Users/sanjee/Documents/projects/s8njee-web/DEPLOY.md)
- [k8s/README.md](/Users/sanjee/Documents/projects/s8njee-web/k8s/README.md)

## Storage Modes

- For Kubernetes, media is expected to live in S3.
- Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, and `AWS_S3_REGION_NAME` in the deployed secret material to store uploaded media in S3.
- Static files are collected during container startup.

## Media And Static

- Local development uses the filesystem for media by default and writes static assets into `staticfiles/`.
- Production uses S3 for uploaded media and still collects static assets during container startup.
- If you switch between those modes, keep the S3 bucket, `MEDIA_ROOT`, and `STATIC_ROOT` assumptions aligned with the deployment target.

## Backup And Restore

### PostgreSQL

To create a logical backup from the current blog database:

```bash
kubectl exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  > backups/s8njee-current.sql
```

To restore into the dedicated blog database:

```bash
kubectl exec -i -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backups/s8njee-current.sql
```

If you need a clean overwrite, drop and recreate the `public` schema before restoring, then rerun `manage.py migrate` if necessary.

### Media

Uploaded media lives in S3 in production. Back up and restore the bucket contents separately from the database:

```bash
aws s3 sync s3://s8njee-photoblog/media/ backups/media/
aws s3 sync backups/media/ s3://s8njee-photoblog/media/
```

## Seed Data

- Fresh empty deployments are seeded from [`blog/fixtures/seed_content.json`](blog/fixtures/seed_content.json).
- The seed fixture contains live content for `posts.post`, `albums.album`, and `albums.photo`.
- Photo rows reference media object keys only. To render images correctly on a seeded environment, point the app at the same S3 bucket or restore the matching media files separately.

## Frontend Stack

The site uses Django templates with vanilla CSS. There is no separate Webpack or Tailwind build step.

## Updating

```bash
git push origin main
```

After pushing, Argo CD reconciles the Kubernetes manifests from Git.

## Runtime Checks

```bash
kubectl --context=mars get application s8njee-web-mars -n argocd
kubectl --context=mars get deploy,pods,svc,pvc,sealedsecret,secret -n default | rg 's8njee'
kubectl --context=mars rollout status deploy/s8njee-web -n default
```

For basic launch observability and smoke testing:

```bash
kubectl logs -n s8njee-web deploy/s8njee-web --tail=200
curl -I https://blog.s8njee.com
curl -I https://argo.s8njee.com
```

## Deployment Checklist

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for general release checks, [DEPLOY.md](/Users/sanjee/Documents/projects/s8njee-web/DEPLOY.md) for safe `mars` deployment steps, and [k8s/README.md](/Users/sanjee/Documents/projects/s8njee-web/k8s/README.md) for manifest layout and Argo CD details.
