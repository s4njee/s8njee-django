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
  - `netcup`, which now includes its own PostgreSQL 18 instance in the `s8njee-web` namespace
  - `mars`, which includes a separate PostgreSQL deployment, PVC, and service for this app
- Overlay-specific `ConfigMap`, secret inputs, and access manifests
- Argo CD `Application` manifests in `k8s/argocd/` that point at each overlay
- Argo CD Image Updater for the netcup overlay so image tags move without Git deploy commits

## Important Assumptions

- Media is stored in S3, so there is no persistent volume for uploads in this manifest set.
- The app currently runs migrations and seed loading during container startup, so the deployment is pinned to `replicas: 1`. If you want horizontal scaling later, split migrations and seeding into a separate `Job`.

## Build And Push The Image

Build from the Django app directory:

```bash
docker build -t registry.s8njee.com/s8njee-web:<tag> ./blog
docker push registry.s8njee.com/s8njee-web:<tag>
```

Netcup no longer needs a manifest commit after this step. The Image Updater controller watches the registry, updates `s8njee-web-netcup` when a newer image appears, and Argo CD syncs that change automatically.

## Argo CD

These manifests do not need a full rewrite for Argo CD. Argo CD supports Kustomize natively, so the main shift is:

- point an Argo CD `Application` at `k8s/overlays/netcup` or `k8s/overlays/mars`
- keep each overlay fully renderable from Git
- move away from local-only secret inputs

This repo now includes:

- `k8s/argocd/argocd-image-updater-install.yaml`
- `k8s/argocd/image-updater.yaml`
- `k8s/argocd/netcup-application.yaml`
- `k8s/argocd/mars-application.yaml`
- `k8s/argocd/argo-server-certificate.yaml`
- `k8s/argocd/argo-server-ingressroute.yaml`
- `k8s/argocd/argo-server-servers-transport.yaml`
- `k8s/argocd/kustomization.yaml`

Before applying them, update `repoURL` in each `Application` to your real Git remote, and pin `targetRevision` to the branch or tag you want Argo CD to sync.

Install both applications with:

```bash
kubectl apply -n argocd -k k8s/argocd
```

That stack also installs Argo CD Image Updater and the `ImageUpdater` custom resource for `s8njee-web-netcup`.

Or install one environment at a time with:

```bash
kubectl apply -n argocd -f k8s/argocd/netcup-application.yaml
kubectl apply -n argocd -f k8s/argocd/mars-application.yaml
```

The same `k8s/argocd` Kustomize stack also exposes Argo CD at `https://argo.s8njee.com` through Traefik using the existing `argocd-server` Service.

To log in with the CLI:

```bash
argocd login argo.s8njee.com \
  --grpc-web \
  --username admin \
  --password "$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
```

### Secrets Under Argo CD

Argo CD can only sync what is available in Git or already present in the cluster. These overlays now use Bitnami Sealed Secrets so the repo can store encrypted secret material instead of plaintext values.

The committed SealedSecret files are scaffolds only. Replace each `AgReplaceWithKubeseal` value with real encrypted output from `kubeseal` before syncing.

Install the Sealed Secrets controller in the target cluster first, then generate sealed values per overlay. One straightforward workflow is:

```bash
cat > k8s/overlays/netcup/secret.unsealed.yaml <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: s8njee-web-secrets
  namespace: s8njee-web
type: Opaque
stringData:
  SECRET_KEY: "your-real-django-secret"
  DB_USER: "s8njee"
  DB_PASSWORD: "your-real-db-password"
  POSTGRES_USER: "s8njee"
  POSTGRES_PASSWORD: "your-real-db-password"
  POSTGRES_DB: "s8njee"
  AWS_ACCESS_KEY_ID: "your-real-aws-key"
  AWS_SECRET_ACCESS_KEY: "your-real-aws-secret"
EOF

kubeseal \
  --format yaml \
  --namespace s8njee-web \
  < k8s/overlays/netcup/secret.unsealed.yaml \
  > k8s/overlays/netcup/sealed-secret.yaml
rm k8s/overlays/netcup/secret.unsealed.yaml
```

Repeat the same pattern for `mars`, including the PostgreSQL keys in the unsealed input secret.

If your controller name or namespace differs from the defaults, add `--controller-name` and `--controller-namespace` to `kubeseal`.

## Overlays

### Netcup

The `netcup` overlay includes:

- app deployment and service
- PostgreSQL 18 StatefulSet
- namespaced PostgreSQL services for app access and StatefulSet identity
- a StatefulSet-managed persistent volume claim
- HTTPS ingress
- an init container that waits for PostgreSQL before the Django app starts

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
- for `netcup`, `DB_HOST` is already wired to the in-cluster PostgreSQL service
- `k8s/overlays/netcup/sealed-secret.yaml`
  - replace the placeholder encrypted values with real `kubeseal` output
- `k8s/overlays/mars/configmap.yaml`
  - adjust the IP-based `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` values if you will access the service another way
- `k8s/overlays/mars/sealed-secret.yaml`
  - replace the placeholder encrypted values with real `kubeseal` output

## Verify

```bash
kubectl -n <namespace> get pods,svc,pvc
kubectl -n <namespace> logs deploy/s8njee-web
kubectl -n <namespace> rollout status deploy/s8njee-web
```

For netcup specifically:

```bash
kubectl --context=netcup get pods,svc,pvc -n s8njee-web
kubectl --context=netcup rollout status statefulset/s8njee-postgres -n s8njee-web
kubectl --context=netcup rollout status deployment/s8njee-web -n s8njee-web
```
