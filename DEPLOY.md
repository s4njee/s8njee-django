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
3. `manage.py collectstatic --noinput`
4. start Uvicorn on port `8000`

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

Production media is stored in S3. Uploaded album photos and blog post images are object keys in `s8njee-photoblog`, such as `photos/...` and `blog-images/...`.

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

The `freya` overlay still exists, but it is not the public Netcup deployment.

Freya uses:

- Argo CD `Application`: `s8njee-web-freya`
- namespace: `default`
- manifests: `k8s/overlays/freya`
- service access: `http://192.168.1.248:4201/`
- PostgreSQL PVC: `s8njee-postgres-data`

For Freya-specific deploys:

```bash
kubectl --context=freya get application s8njee-web-freya -n argocd
kubectl --context=freya get deploy,pods,svc,pvc,sealedsecret,secret -n default | rg 's8njee'
kubectl --context=freya rollout status deploy/s8njee-web -n default
kubectl --context=freya rollout status deploy/s8njee-postgres -n default
```

Do not delete or rename `s8njee-postgres-data` unless you are intentionally replacing the Freya database.
