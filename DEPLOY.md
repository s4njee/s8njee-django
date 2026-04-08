# Deploy

This project is deployed to Kubernetes with Argo CD.

The current `mars` deployment uses these persistent database resources:

- `StatefulSet`: `s8njee-postgres`
- `Service`: `s8njee-postgres`
- `PersistentVolumeClaim`: `s8njee-postgres-data`
- `Secret`: `s8njee-web-secrets` generated from the committed `SealedSecret`

## Safe Deploy Rule

If you want to deploy a new app version without overwriting the PostgreSQL database, do not delete or rename:

- `k8s/overlays/mars/postgres-pvc.yaml`
- the PVC name `s8njee-postgres-data`
- the PostgreSQL StatefulSet name `s8njee-postgres`
- the database keys inside `k8s/overlays/mars/sealed-secret.yaml`

Argo CD can safely roll the app forward in place as long as those resources keep the same identity.

## Normal Mars Deploy

1. Build and push a new app image.
2. Update the image tag in [`k8s/overlays/mars/kustomization.yaml`](/Users/sanjee/Documents/projects/s8njee-web/k8s/overlays/mars/kustomization.yaml).
3. Commit and push to `main`.
4. Let Argo CD sync `s8njee-web-mars` from `https://github.com/s4njee/s8njee-django.git`.

That flow updates the Django app without recreating the PostgreSQL volume.

## Startup Flow

The release entrypoint is [`blog/start.sh`](/Users/sanjee/Documents/projects/s8njee-web/blog/start.sh).

It is the canonical production startup path and always runs these steps in order:

1. `manage.py migrate`
2. load seed content only if the database is empty
3. `manage.py collectstatic`
4. start Uvicorn

For local development, use `cd blog && uv sync && uv run python manage.py migrate && uv run python manage.py runserver`.

## What Not To Do

Do not run these as part of a normal deploy:

- `kubectl delete pvc s8njee-postgres-data -n default`
- `kubectl delete -k k8s/overlays/mars`
- `kubectl delete application s8njee-web-mars -n argocd` followed by PVC cleanup
- changing the PVC name in `k8s/overlays/mars/postgres-pvc.yaml`
- rotating `DB_PASSWORD`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` unless you are doing a planned database credential change

Those actions can orphan or replace the running database.

## Updating Secrets Safely

If you need to change app or database secrets on `mars`:

1. Start from the live cluster secret so you preserve the current DB values.
2. Edit only the keys you intend to rotate.
3. Reseal the secret against the `mars` cluster.
4. Commit the updated `k8s/overlays/mars/sealed-secret.yaml`.

Example:

```bash
kubectl --context=mars get secret s8njee-web-secrets -n default -o json \
  | jq '{apiVersion:"v1",kind:"Secret",metadata:{name:.metadata.name,namespace:.metadata.namespace},type:.type,data:.data}' \
  | kubeseal --controller-name=sealed-secrets --controller-namespace=kube-system --context mars --format yaml \
  > k8s/overlays/mars/sealed-secret.yaml
```

If you are not intentionally rotating database credentials, keep these values logically unchanged:

- `DB_USER`
- `DB_PASSWORD`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

## Verifying The Database Was Preserved

After Argo syncs:

```bash
kubectl --context=mars get application s8njee-web-mars -n argocd
kubectl --context=mars get deploy,pods,svc,pvc,sealedsecret,secret -n default | rg 's8njee'
kubectl --context=mars rollout status deploy/s8njee-web -n default
kubectl --context=mars rollout status deploy/s8njee-postgres -n default
```

Confirm:

- `s8njee-web-mars` is `Synced` and `Healthy`
- `s8njee-postgres-data` is still `Bound`
- `s8njee-postgres` is still using the same PVC
- the site responds on `http://192.168.1.156:4201/`

## Backup And Restore

### PostgreSQL

Create a dump from the live Mars database:

```bash
kubectl exec -n default postgres-0 -- \
  sh -lc 'PGPASSWORD=postgres pg_dump -U postgres -d s8njee --no-owner --no-privileges' \
  > backups/mars-postgres.sql
```

Restore a dump into Mars:

```bash
kubectl exec -i -n default postgres-0 -- \
  sh -lc 'PGPASSWORD=postgres psql -U postgres -d s8njee' \
  < backups/mars-postgres.sql
```

### Media

Media is stored in S3 in production, so bucket sync is separate from PostgreSQL backup:

```bash
aws s3 sync s3://s8njee-photoblog/media/ backups/media/
aws s3 sync backups/media/ s3://s8njee-photoblog/media/
```

## Smoke Checks

After any deploy, verify:

```bash
kubectl logs -n default deploy/s8njee-web --tail=200
curl -I http://192.168.1.156:4201/
kubectl exec -n default deploy/s8njee-web -- python manage.py migrate --check
```

## If You Need To Rebuild The App But Keep The DB

It is safe to change:

- the Django image tag
- app template files
- Python dependencies
- probes, resource limits, and service settings

It is not safe to change casually:

- the PVC name
- the namespace for the DB objects
- the PostgreSQL data mount path
- database credential values

Treat the PVC and DB credentials as the boundary between a routine deploy and a database migration.
