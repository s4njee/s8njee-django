# Deploy

This project is deployed to Kubernetes with Argo CD.

The primary deployment is the `freya` cluster, serving `http://192.168.1.248:4201/` for LAN and dev testing.

## Freya Deploy Flow

Freya pulls from a LAN HTTP registry on `192.168.1.248:5001`.

### 1. Build and Push Image

If local Docker cannot reach `ssh://freya.local`, sync the working tree to Freya and build from there:

```bash
# Sync local changes to the Freya node
rsync -az --delete --exclude .git --exclude .idea ./ freya.local:/home/sanjee/tmp/s8njee-web/

# Build and push from the Freya node
TAG="sha-$(git rev-parse HEAD)"
ssh freya.local "cd /home/sanjee/tmp/s8njee-web/blog && docker buildx build --platform linux/amd64 --push -t 192.168.1.248:5001/s8njee-web:${TAG} ."
```

### 2. Update Manifests

Update `k8s/overlays/freya/kustomization.yaml` with the new tag:

```bash
# Update the image tag in kustomization
cd k8s/overlays/freya
kustomize edit set image s8njee-web=192.168.1.248:5001/s8njee-web:${TAG}
```

### 3. Apply to Cluster

Freya deploys are manually applied (Argo CD is present but typically bypassed for this overlay):

```bash
kubectl --context=freya apply -k k8s/overlays/freya
kubectl --context=freya rollout status deploy/s8njee-web -n default
```

## Freya Verification

Check Kubernetes resources:

```bash
kubectl --context=freya get deploy,pods,svc,pvc,sealedsecret,secret -n default | rg 's8njee'
kubectl --context=freya rollout status deploy/s8njee-web -n default
kubectl --context=freya rollout status deploy/s8njee-postgres -n default
curl -I http://192.168.1.248:4201/
```

## Startup Flow

The release entrypoint is `blog/start.sh`. It always runs:
1. `manage.py migrate --noinput`
2. load `fixtures/seed_content.json` if site is empty
3. `manage.py collectstatic --noinput`
4. start Uvicorn on port `8000`

---

## Netcup (Legacy/Secondary)

The `netcup` overlay was the previous production deployment. It serves `https://blog.s8njee.com`.

- Argo CD `Application`: `s8njee-web-netcup`
- Kubernetes namespace: `s8njee-web`
- App image: `registry.s8njee.com/s8njee-web:<tag>`
- App manifests: `k8s/overlays/netcup`

### Netcup Deploy Flow

Netcup deploys are image-driven via Argo CD Image Updater.

```bash
TAG="sha-$(git rev-parse HEAD)"
docker buildx build --platform linux/amd64 --push \
  -t "registry.s8njee.com/s8njee-web:${TAG}" \
  ./blog
```

## Secrets

Freya and Netcup both use Bitnami Sealed Secrets.
- Freya: `k8s/overlays/freya/sealed-secret.yaml`
- Netcup: `k8s/overlays/netcup/sealed-secret.yaml`

To rotate:
```bash
kubectl --context=freya get secret s8njee-web-secrets -n default -o json \
  | jq '{apiVersion:"v1",kind:"Secret",metadata:{name:.metadata.name,namespace:.metadata.namespace},type:.type,data:.data}' \
  | kubeseal --context=freya --namespace=default --format yaml \
  > k8s/overlays/freya/sealed-secret.yaml
```

## Backups

### PostgreSQL (Freya)
```bash
kubectl --context=freya exec deploy/s8njee-web -n default -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  > backups/freya-postgres.sql
```

### Media (S3)
```bash
aws s3 sync s3://s8njee-photoblog/ backups/s8njee-photoblog/
```
