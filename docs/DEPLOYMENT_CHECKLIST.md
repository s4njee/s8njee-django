# Deployment Checklist

Use this checklist before each production release to Netcup.

---

## 1. Prepare Secrets

- Confirm `k8s/overlays/netcup/sealed-secret.yaml` contains up-to-date sealed values for all required keys:
  - `SECRET_KEY`, `DB_USER`, `DB_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME` (S3 or Backblaze B2)
- If rotating credentials, reseal with `kubeseal` and commit before deploying. See `DEPLOY.md` → Secrets.

## 2. Stage Migrations

- Any new Django migrations must be copied to `deploy/netcup/migrations/<app>/` before the release.
- Currently staged: `albums/0005` through `albums/0008`.
- After a successful Netcup rollout, verify the pod logs show the migrations applied, then clear the staged copies.

## 3. Build and Push the Image

```bash
TAG="sha-$(git rev-parse --short HEAD)"
docker buildx build --platform linux/amd64 --push \
  -t "registry.s8njee.com/s8njee-web:${TAG}" \
  ./blog
```

Argo CD Image Updater will detect the new tag and update the live deployment automatically. No manifest commit needed.

## 4. Verify the Rollout

```bash
# Argo CD application status
kubectl --context=netcup get application s8njee-web-netcup -n argocd

# Kubernetes rollout
kubectl --context=netcup rollout status deploy/s8njee-web -n s8njee-web
kubectl --context=netcup rollout status statefulset/s8njee-postgres -n s8njee-web

# Pod logs — confirm migrations ran and no startup errors
kubectl --context=netcup logs -n s8njee-web deploy/s8njee-web --tail=200
```

## 5. Smoke Check

- `curl -I https://blog.s8njee.com/` returns 200
- `curl -I https://blog.s8njee.com/photos/` returns 200
- Log into `/admin/` and confirm posts and albums are accessible
- Upload a test image and confirm it lands in the configured storage backend (S3 or B2)

## 6. Post-Deploy Cleanup

- Clear staged migrations from `deploy/netcup/migrations/` once the rollout is confirmed healthy.
- Update `docs/ToDo.md` if any open items were resolved by this release.

---

## Safe Deploy Rules

Do not delete or rename these resources during a normal app deploy:

- namespace `s8njee-web`
- StatefulSet `s8njee-postgres` and its services
- StatefulSet volume claim template name `data` (the live PVC)
- secret `s8njee-web-secrets`
- secret keys `DB_USER`, `DB_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

These are the boundary between a routine app rollout and a database replacement or credential rotation.
