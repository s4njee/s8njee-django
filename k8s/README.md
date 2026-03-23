# Kubernetes Deployment

These manifests deploy the Django app directly behind a Traefik ingress controller.

## What Is Included

- A base `Deployment` that runs the existing container entrypoint, which performs:
  - migrations
  - one-time seed loading on an empty database
  - `collectstatic`
  - Uvicorn startup
- A `Service` exposing the app on port 80 inside the cluster
- Environment-specific overlays for:
  - `netcup`, where PostgreSQL is expected to exist outside the manifest set
  - `mars`, which includes a separate PostgreSQL deployment, PVC, and service for this app
- Overlay-specific `ConfigMap`, secret inputs, and access manifests

## Important Assumptions

- Media is stored in S3, so there is no persistent volume for uploads in this manifest set.
- The app currently runs migrations and seed loading during container startup, so the deployment is pinned to `replicas: 1`. If you want horizontal scaling later, split migrations and seeding into a separate `Job`.

## Build And Push The Image

Build from the Django app directory:

```bash
docker build -t registry.s8njee.com/s8njee-web:<tag> ./blog
docker push registry.s8njee.com/s8njee-web:<tag>
```

Then update the target overlay `kustomization.yaml` with the real image name and tag.

## Overlays

### Netcup

The `netcup` overlay expects an existing PostgreSQL endpoint and HTTPS ingress.

Apply with:

```bash
kubectl --context=netcup apply -k k8s/overlays/netcup
```

### Mars

The `mars` overlay includes:

- app deployment and service
- PostgreSQL deployment
- PostgreSQL PVC using `local-path`
- PostgreSQL service
- a `LoadBalancer` service on port `4201`
- an init container that waits for PostgreSQL before the Django app starts
- an image pull secret reference for the in-cluster registry

Apply with:

```bash
kubectl --context=mars apply -k k8s/overlays/mars
```

## Configure The Overlay

Edit these files before applying:

- `k8s/overlays/<overlay>/configmap.yaml`
  - set `ALLOWED_HOSTS`
  - set `CSRF_TRUSTED_ORIGINS`
- for `netcup`, set `DB_HOST`
- `k8s/overlays/netcup/secret.yaml`
  - set `SECRET_KEY`
  - set `DB_PASSWORD`
  - set AWS credentials
- `k8s/overlays/mars/configmap.yaml`
  - adjust the IP-based `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` values if you will access the service another way
- `k8s/overlays/mars/secret.env`
  - create it from `k8s/overlays/mars/secret.env.example`
  - keep it local; it is ignored by git

## Verify

```bash
kubectl -n <namespace> get pods,svc,pvc
kubectl -n <namespace> logs deploy/s8njee-web
kubectl -n <namespace> rollout status deploy/s8njee-web
```
