# Development Notes

This document describes the current architecture of `s8njee-web` and the deployment paths that exist in the repo today.

## Architecture

The active application is a single Django project in [`../blog/`](../blog).

- Blog routes live at `/`
- Photo gallery routes live at `/photos/`
- `posts` is the blog app
- `albums` is the photo gallery app
- Django is served directly by Uvicorn
- static files are collected into `staticfiles/`
- uploaded media is expected to live in S3 in production

The app startup path is [`../blog/start.sh`](../blog/start.sh). On container boot it:

1. runs `manage.py migrate`
2. checks whether posts or albums already exist
3. loads [`../blog/fixtures/seed_content.json`](../blog/fixtures/seed_content.json) on an empty database
4. runs `manage.py collectstatic`
5. starts Uvicorn on port `8000`

Important consequence: the current production model is single-replica startup with migrations and seeding happening in-process. If we want horizontal scaling later, this should become a separate migration/seed `Job`.

## Data Model

The main persisted data currently comes from:

- PostgreSQL for app data
- S3 for image/media objects

The production-derived Django seed fixture contains:

- `posts.post`
- `albums.album`
- `albums.photo`

That fixture is app content only. It does not include the binary media objects in S3.

## Repo Layout

- [`../blog/`](../blog): active Django application
- [`../k8s/`](../k8s): Kubernetes manifests
- [`../backups/`](../backups): pulled database dumps
- [`../archive/photos-standalone-app/`](../archive/photos-standalone-app): retired standalone photo service

## Local Development

Create local env files from examples:

```bash
cp .env.example .env
cp blog/.env.example blog/.env
cp db.env.example db.env
```

For a lightweight local run, leave `DB_*` blank in `blog/.env` so Django uses SQLite.

Run locally:

```bash
cd blog
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The app will be available at:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/photos/`

## Container Build

The container build context is [`../blog`](../blog), using [`../blog/Dockerfile`](../blog/Dockerfile).

General build:

```bash
docker build -t <registry>/<image>:<tag> ./blog
docker push <registry>/<image>:<tag>
```

For Freya, the cluster can currently pull from the LAN registry endpoint `192.168.1.248:5001`.

Current Freya image:

- `192.168.1.248:5001/s8njee-web:20260323-184500-amd64`

To build an amd64 image explicitly:

```bash
docker buildx build \
  --platform linux/amd64 \
  -t 192.168.1.248:5001/s8njee-web:<tag> \
  --push \
  ./blog
```

To verify image architecture:

```bash
docker buildx imagetools inspect 192.168.1.248:5001/s8njee-web:<tag>
```

## Kubernetes

Base manifests live in [`../k8s/base/`](../k8s/base). Environment-specific configuration lives in overlays.

### Freya

The main active Kubernetes deployment path is [`../k8s/overlays/freya/`](../k8s/overlays/freya).

What it deploys:

- `s8njee-web` Django deployment
- `s8njee-postgres` PostgreSQL deployment
- `s8njee-postgres-data` PVC
- `s8njee-web` `LoadBalancer` service on port `4201`
- `s8njee-postgres` internal `ClusterIP` service

Current Freya assumptions:

- namespace: `default`
- image pull secret: `regcred`
- registry address reachable from cluster: `192.168.1.248:5001`
- service address: `http://192.168.1.248:4201/`
- DB host inside cluster: `s8njee-postgres`
- storage class for Postgres PVC: `local-path`

Important manifest files:

- [`../k8s/overlays/freya/kustomization.yaml`](../k8s/overlays/freya/kustomization.yaml)
- [`../k8s/overlays/freya/configmap.yaml`](../k8s/overlays/freya/configmap.yaml)
- `k8s/overlays/freya/secret.env` (local only, ignored by git)
- [`../k8s/overlays/freya/secret.env.example`](../k8s/overlays/freya/secret.env.example)
- [`../k8s/overlays/freya/postgres-deployment.yaml`](../k8s/overlays/freya/postgres-deployment.yaml)
- [`../k8s/overlays/freya/service-patch.yaml`](../k8s/overlays/freya/service-patch.yaml)
- [`../k8s/overlays/freya/deployment-patch.yaml`](../k8s/overlays/freya/deployment-patch.yaml)

Render manifests:

```bash
kubectl kustomize k8s/overlays/freya
```

Client-side validation:

```bash
kubectl apply --dry-run=client -k k8s/overlays/freya
```

Apply:

```bash
cp k8s/overlays/freya/secret.env.example k8s/overlays/freya/secret.env
kubectl --context=freya apply -k k8s/overlays/freya
```

Verify:

```bash
kubectl --context=freya get pods,svc,pvc -n default | rg s8njee
kubectl --context=freya rollout status deployment/s8njee-postgres -n default
kubectl --context=freya rollout status deployment/s8njee-web -n default
curl -I http://192.168.1.248:4201/
```

### Netcup

The Netcup overlay is [`../k8s/overlays/netcup/`](../k8s/overlays/netcup).

That path assumes:

- the `s8njee-web` namespace contains both the Django app and the dedicated PostgreSQL 18 instance
- Traefik ingress
- external hostname/TLS routing rather than a `LoadBalancer` on `4201`
- the app waits for PostgreSQL before starting

What it deploys:

- `s8njee-web` Django deployment
- `s8njee-postgres` PostgreSQL StatefulSet
- a PostgreSQL headless service for StatefulSet identity
- a PostgreSQL `ClusterIP` service for the app and backup job
- a namespaced PostgreSQL volume claim managed by the StatefulSet

Apply:

```bash
kubectl --context=netcup apply -k k8s/overlays/netcup
```

Verify:

```bash
kubectl --context=netcup get pods,svc,pvc -n s8njee-web | rg 's8njee'
kubectl --context=netcup rollout status statefulset/s8njee-postgres -n s8njee-web
kubectl --context=netcup rollout status deployment/s8njee-web -n s8njee-web
```

## Secrets And Caution

The Freya overlay now reads its secrets from `k8s/overlays/freya/secret.env`, which is intentionally ignored by git.

That keeps the active deployment path usable without storing Freya secrets in tracked manifest files.

Recommended next cleanup:

1. move Kubernetes secrets out of git
2. recreate them with `kubectl create secret` or a secret manager workflow
3. rotate Django, PostgreSQL, and AWS credentials after the migration

## Useful Commands

Freya rollout status:

```bash
kubectl --context=freya rollout status deployment/s8njee-web -n default
kubectl --context=freya rollout status deployment/s8njee-postgres -n default
```

Freya logs:

```bash
kubectl --context=freya logs deployment/s8njee-web -n default --tail=200
kubectl --context=freya logs deployment/s8njee-postgres -n default --tail=200
```

Check the active image in the running pod:

```bash
kubectl --context=freya get pod -n default -o wide | rg s8njee-web
kubectl --context=freya describe pod <pod-name> -n default
```
