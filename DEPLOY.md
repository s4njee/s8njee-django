# Deploy

This project is deployed to Kubernetes with Argo CD.

The public production deployment is the `netcup` cluster. It serves `https://blog.s8njee.com` through Traefik and uses:

- Argo CD `Application`: `s8njee-web-netcup`
- Kubernetes namespace: `s8njee-web`
- App image: `registry.s8njee.com/s8njee-web:<tag>`
- App manifests: `k8s/overlays/netcup`
- Django deployment: `s8njee-web`
- PostgreSQL StatefulSet: `s8njee-postgres`
- PostgreSQL pod: `s8njee-postgres-0`
- PostgreSQL services: `s8njee-postgres` and `s8njee-postgres-headless`
- App secret: `s8njee-web-secrets`, generated from the committed `SealedSecret`
- Registry pull secret: `registry-s8njee-pull`, generated from the committed `SealedSecret`
- Media storage: S3 bucket `s8njee-photoblog`

## Netcup Deploy Flow

Netcup deploys are image-driven. Build and push a new image tag, then let Argo CD Image Updater point the `s8njee-web-netcup` application at the newest image.

From the repo root:

```bash
TAG="sha-$(git rev-parse HEAD)"
docker buildx build --platform linux/amd64 --push \
  -t "registry.s8njee.com/s8njee-web:${TAG}" \
  ./blog
```

After the image is pushed:

1. Argo CD Image Updater watches `registry.s8njee.com/s8njee-web`.
2. It updates the `s8njee-web-netcup` Argo CD application in-cluster.
3. Argo CD syncs `k8s/overlays/netcup`.
4. Kubernetes rolls the `s8njee-web` deployment.
5. `blog/start.sh` runs migrations, seed loading if the DB is empty, `collectstatic`, then starts Uvicorn.

You normally do not need to edit `k8s/overlays/netcup/kustomization.yaml` for an app deploy. The checked-in image tag is only the Git baseline; Image Updater moves the live Netcup application after a newer registry tag exists.

### Netcup Migration Queue

Use `deploy/netcup/migrations/` as the staging area for Django migrations that still need to reach Netcup.

- When you add a new migration under `blog/<app>/migrations/`, copy the same file into `deploy/netcup/migrations/<app>/` before you consider the change ready for Netcup.
- Keep the staged copy in git until the Netcup rollout has applied it.
- The currently staged migrations are:
  - `deploy/netcup/migrations/albums/0005_alter_photo_options_photo_sort_order.py`
  - `deploy/netcup/migrations/albums/0006_album_cover_photo.py`
  - `deploy/netcup/migrations/albums/0007_photo_image_variants.py`
  - `deploy/netcup/migrations/albums/0008_album_slug_photo_alt_text.py`
- When it is time to deploy to Netcup, make sure the staged migration folder matches the real app migrations, then ship the normal Netcup release as usual.
- After the rollout, verify the pod logs show the new migrations being applied, then clear the staged copies once Netcup is up to date.

If you need to force the migration step manually on Netcup, run:

```bash
kubectl --context=netcup exec -n s8njee-web deploy/s8njee-web -- \
  sh -lc 'cd /app && DJANGO_SETTINGS_MODULE=blog.settings.production uv run python manage.py migrate --noinput'
```

## Netcup First-Time Or Manual Apply

The Argo CD application points at:

- repo: `https://github.com/s4njee/s8njee-django.git`
- branch: `main`
- path: `k8s/overlays/netcup`
- destination namespace: `s8njee-web`

Install or refresh the Argo CD stack:

```bash
kubectl --context=netcup apply -n argocd -k k8s/argocd
```

Apply only the Netcup application:

```bash
kubectl --context=netcup apply -n argocd -f k8s/argocd/netcup-application.yaml
```

Apply the Netcup overlay directly only when you are intentionally bypassing Argo CD:

```bash
kubectl --context=netcup apply -k k8s/overlays/netcup
```

## Netcup Verification

Check Argo CD:

```bash
kubectl --context=netcup get application s8njee-web-netcup -n argocd
kubectl --context=netcup get imageupdater s8njee-web-netcup -n argocd
```

Check Kubernetes rollout:

```bash
kubectl --context=netcup get pods,svc,pvc,sealedsecret,secret -n s8njee-web | rg 's8njee|registry'
kubectl --context=netcup rollout status statefulset/s8njee-postgres -n s8njee-web
kubectl --context=netcup rollout status deployment/s8njee-web -n s8njee-web
```

Check logs and HTTP:

```bash
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-web --tail=200
curl -I https://blog.s8njee.com/
```

Confirm:

- `s8njee-web-netcup` is synced and healthy.
- `s8njee-postgres-0` is ready.
- The StatefulSet-managed PVC is still bound.
- The deployed app pod is running an image from `registry.s8njee.com/s8njee-web`.
- `https://blog.s8njee.com/` returns a successful response.

## Netcup Safe Deploy Rule

Routine app deploys should only change the app image, app code, templates, Python dependencies, config, probes, or resource limits.

Do not delete or rename these during a normal deploy:

- namespace `s8njee-web`
- StatefulSet `s8njee-postgres`
- services `s8njee-postgres` and `s8njee-postgres-headless`
- StatefulSet volume claim template name `data`
- live PVC created for `s8njee-postgres-0`
- secret `s8njee-web-secrets`
- secret keys `DB_USER`, `DB_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`

Those resources are the boundary between a routine app rollout and a database replacement or credential rotation.

## Startup Flow

The release entrypoint is `blog/start.sh`.

It is the canonical production startup path and always runs these steps in order:

1. `manage.py migrate --noinput`
2. load `fixtures/seed_content.json` only if the site has no posts or albums
3. `manage.py backfill_photo_sort_order`
4. `manage.py backfill_album_slugs`
5. `manage.py backfill_image_variants`
6. `manage.py collectstatic --noinput`
7. start Uvicorn on port `8000`

The deployment is intentionally pinned to one app replica because startup currently owns migrations and seed loading.

## Secrets

Netcup uses Bitnami Sealed Secrets so encrypted secret material can live in Git.

The important files are:

- `k8s/overlays/netcup/sealed-secret.yaml`
- `k8s/overlays/netcup/registry-pull-sealed-secret.yaml`

To rotate app secrets safely, start from the live secret, change only the keys you intend to rotate, reseal it for the `s8njee-web` namespace, then commit the updated sealed secret.

Example:

```bash
kubectl --context=netcup get secret s8njee-web-secrets -n s8njee-web -o json \
  | jq '{apiVersion:"v1",kind:"Secret",metadata:{name:.metadata.name,namespace:.metadata.namespace},type:.type,data:.data}' \
  | kubeseal --context=netcup --namespace=s8njee-web --format yaml \
  > k8s/overlays/netcup/sealed-secret.yaml
```

If you are not intentionally rotating database credentials, keep these values logically unchanged:

- `DB_USER`
- `DB_PASSWORD`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

## Backups

### PostgreSQL

Create a dump from the live Netcup database:

```bash
kubectl --context=netcup exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  > backups/netcup-postgres.sql
```

Restore a dump into Netcup:

```bash
kubectl --context=netcup exec -i -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backups/netcup-postgres.sql
```

### Media

Production media is stored in S3 (migrating to Backblaze B2 — see `docs/Engineering.md`). Uploaded album photos and blog post images are object keys in `s8njee-photoblog`, such as `photos/...` and `blog-images/...`.

Back up the bucket before destructive media changes:

```bash
aws s3 sync s3://s8njee-photoblog/ backups/s8njee-photoblog/
```

Restore from a local bucket backup:

```bash
aws s3 sync backups/s8njee-photoblog/ s3://s8njee-photoblog/
```

## Troubleshooting

Check which image is running:

```bash
kubectl --context=netcup get deploy s8njee-web -n s8njee-web \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Describe an unhealthy pod:

```bash
kubectl --context=netcup describe pod -n s8njee-web <pod-name>
```

Check Django startup errors:

```bash
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-web --tail=300
```

Check PostgreSQL:

```bash
kubectl --context=netcup logs -n s8njee-web statefulset/s8njee-postgres --tail=200
kubectl --context=netcup exec -n s8njee-web s8njee-postgres-0 -- \
  sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## Freya

The `freya` overlay is the secondary/dev deployment. It is useful for LAN testing and recovery work, but it is not the public Netcup deployment.

Freya uses:

- namespace: `default`
- manifests: `k8s/overlays/freya`
- service access: `http://192.168.1.248:4201/`
- app image registry for the base runtime image: `192.168.1.248:5001`
- app image pull secret: `regcred`
- dev source path on the Freya host: `/home/sanjee/tmp/s8njee-web/blog`
- PostgreSQL image: `postgres:18.3-alpine3.23`
- PostgreSQL PVC: `s8njee-postgres-data-freya`
- PostgreSQL placement: pinned to node `freya`
- Celery broker: `valkey` in the same namespace
- Celery worker: `s8njee-celery-worker`

Freya does have Argo CD installed. The `s8njee-web-freya` Argo CD Application manifest is at `k8s/argocd/freya-application.yaml`. It tracks the `freya` branch, so Argo CD will only stay green when that branch exists and is pushed.

For Freya-specific health checks:

```bash
kubectl --context=freya get deploy,pods,svc,pvc,sealedsecret,secret -n default | rg 's8njee'
kubectl --context=freya rollout status deploy/s8njee-web -n default
kubectl --context=freya rollout status deploy/s8njee-postgres -n default
kubectl --context=freya rollout status deploy/s8njee-celery-worker -n default
curl -I http://192.168.1.248:4201/
```

### Freya Fast Dev Sync

Freya's default app iteration strategy is source sync, not image rebuilds. Argo CD manages the Kubernetes overlay, while source edits still ride through the hostPath sync path.

The pod still starts from a normal app image so it has Python, `uv`, PostgreSQL client tools, and installed dependencies. The Freya overlay then mounts selected source directories from the Freya node with `hostPath`:

- `/home/sanjee/tmp/s8njee-web/blog/blog`
- `/home/sanjee/tmp/s8njee-web/blog/posts`
- `/home/sanjee/tmp/s8njee-web/blog/albums`
- `/home/sanjee/tmp/s8njee-web/blog/templates`
- `/home/sanjee/tmp/s8njee-web/blog/static`
- `/home/sanjee/tmp/s8njee-web/blog/fixtures`

For normal Python, template, CSS, JS, migration, and fixture edits, sync the source tree to Freya:

```bash
scripts/freya-sync.sh
```

The Freya web container runs Uvicorn with `--reload`, so most source edits restart automatically after the sync. No image build, image push, kustomization tag edit, or `kubectl apply` is needed for ordinary code/template changes.

If the app does not reload, restart only the web deployment:

```bash
kubectl --context=freya rollout restart deploy/s8njee-web -n default
kubectl --context=freya rollout status deploy/s8njee-web -n default
```

The mounted source directories intentionally do not replace all of `/app`; the image still owns the virtual environment, installed Python dependencies, system packages, `manage.py`, `pyproject.toml`, and `uv.lock`.

Freya also runs a local Valkey broker and a Celery worker so queued photo uploads can finish in the background. That means uploads no longer block the web request while RAW files are demosaiced, downscaled, and re-encoded.

When changing Freya manifests, apply the overlay:

```bash
kubectl --context=freya apply -k k8s/overlays/freya
kubectl --context=freya rollout status deploy/s8njee-web -n default
kubectl --context=freya rollout status deploy/s8njee-celery-worker -n default
```

If you want Freya itself to be managed by Argo CD from Git, install the application and image updater once:

```bash
kubectl --context=freya apply -n argocd -f k8s/argocd/freya-application.yaml
kubectl --context=freya apply -n argocd -f k8s/argocd/freya-image-updater.yaml
kubectl --context=freya apply -n default -f k8s/argocd/image-updater-registry-secret-rbac-freya.yaml
```

Rebuild and push a Freya image only when changing dependencies, base runtime behavior, or files that are not mounted from the Freya host, such as:

- `blog/Dockerfile`
- `blog/pyproject.toml`
- `blog/uv.lock`
- system packages
- entrypoint/startup behavior
- files outside the mounted source directories

If the Freya image tag changes, Argo CD Image Updater can write the new tag back into `k8s/overlays/freya/kustomization.yaml` once the Freya image-updater CR is installed.

The quick decision rule is:

- Django code/templates/static/fixtures changed: run `scripts/freya-sync.sh`.
- Freya Kubernetes manifests changed: run `kubectl --context=freya apply -k k8s/overlays/freya`.
- Dependencies or image runtime changed: rebuild and push the Freya image, update `k8s/overlays/freya/kustomization.yaml`, then apply the overlay.
- Photo uploads now queue through Celery on Freya. If the queue seems stuck, check `deploy/s8njee-celery-worker` and `svc/valkey` first.

### Freya Image Build And Registry

Freya still needs a base app image. It pulls that image from a LAN HTTP registry on `192.168.1.248:5001`. Because the registry is HTTP, both Docker and k3s/containerd on `freya` must be configured to allow the registry as insecure.

The k3s registry file on `freya` should include:

```yaml
mirrors:
  "192.168.1.248:5001":
    endpoint:
      - "http://192.168.1.248:5001"
```

After editing `/etc/rancher/k3s/registries.yaml`, restart k3s:

```bash
ssh freya.local 'sudo systemctl restart k3s'
```

The Docker daemon on `freya` also needs `192.168.1.248:5001` in `/etc/docker/daemon.json` under `insecure-registries`, followed by a Docker restart. This matters when building and pushing images from the Freya node itself.

The cluster pull secret must match the new registry address. If pods fail with `authorization failed: no basic auth credentials`, recreate `regcred` for `192.168.1.248:5001`:

```bash
kubectl --context=freya create secret docker-registry regcred \
  --docker-server=192.168.1.248:5001 \
  --docker-username=dummyuser \
  --docker-password='dummy-password' \
  --dry-run=client -o yaml \
  | kubectl --context=freya apply -f -
```

If local Docker cannot reach `ssh://freya.local`, sync the full working tree to Freya and build from there. This is only needed for base image rebuilds, not normal dev edits:

```bash
rsync -az --delete --exclude .git --exclude .idea ./ freya.local:/home/sanjee/tmp/s8njee-web/
ssh freya.local 'cd /home/sanjee/tmp/s8njee-web/blog && docker buildx build --platform linux/amd64 --push -t 192.168.1.248:5001/s8njee-web:<tag> .'
```

Update `k8s/overlays/freya/kustomization.yaml` with the pushed tag, then apply:

```bash
kubectl --context=freya apply -k k8s/overlays/freya
kubectl --context=freya rollout status deploy/s8njee-web -n default
```

### Freya Node Address

The Freya node and service should advertise `192.168.1.248`, not the stale `192.168.1.156`.

Check both values:

```bash
kubectl --context=freya get node freya -o wide
kubectl --context=freya get svc s8njee-web -n default -o wide
```

If the node still shows `EXTERNAL-IP` as `192.168.1.156`, set `/etc/rancher/k3s/config.yaml` on `freya` to:

```yaml
node-external-ip: 192.168.1.248
```

Then restart k3s:

```bash
ssh freya.local 'sudo systemctl restart k3s'
```

The Freya service manifest also pins `loadBalancerIP: 192.168.1.248`, but k3s will keep reporting the stale service address until the node external IP is corrected.

### Freya PostgreSQL

Freya PostgreSQL is currently disposable dev data. The database was recreated on Postgres 18 and reseeded from `blog/fixtures/seed_content.json`.

Do not delete or rename `s8njee-postgres-data-freya` unless you are intentionally replacing the Freya database. If the database is intentionally recreated, the app startup should run migrations and seed the fixture automatically.

One important startup trap: `manage.py` defaults to `blog.settings.development`, which uses SQLite. The production container entrypoint must export `DJANGO_SETTINGS_MODULE=blog.settings.production` before running migrations or `loaddata`; otherwise startup can appear to seed successfully while the live ASGI app still points at empty Postgres and returns HTTP 500.

If Freya returns 500 after a DB recreate, verify that Postgres actually has tables and content:

```bash
kubectl --context=freya exec deploy/s8njee-postgres -n default -- \
  env PGPASSWORD=s8njee-local psql -h 127.0.0.1 -U s8njee -d s8njee -Atc 'select count(*) from posts_post;'

kubectl --context=freya logs deploy/s8njee-web -n default --tail=120
```
