#!/bin/sh
# Dump the netcup postgres DB (read-only) and restore it into freya.
# Netcup: StatefulSet s8njee-postgres-0, namespace s8njee-web
# Freya:  Deployment s8njee-postgres-*, namespace default
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
BACKUP_DIR="$ROOT_DIR/backups"
DUMP_FILE="$BACKUP_DIR/netcup-$(date +%Y%m%d-%H%M%S).sql.gz"

NETCUP_POD="s8njee-postgres-0"
NETCUP_NS="s8njee-web"
FREYA_NS="default"

echo "==> Dumping netcup postgres (read-only)..."
kubectl --context=netcup exec -n "$NETCUP_NS" "$NETCUP_POD" -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip > "$DUMP_FILE"
echo "    Saved to $DUMP_FILE"

echo "==> Locating freya postgres pod..."
FREYA_POD="$(kubectl --context=freya get pod -n "$FREYA_NS" -l app=s8njee-postgres \
  -o jsonpath='{.items[0].metadata.name}')"
echo "    Found: $FREYA_POD"

echo "==> Dropping and recreating public schema on freya..."
kubectl --context=freya exec -n "$FREYA_NS" "$FREYA_POD" -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'

echo "==> Restoring dump into freya..."
gunzip -c "$DUMP_FILE" | \
  kubectl --context=freya exec -i -n "$FREYA_NS" "$FREYA_POD" -- \
  sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q'

echo "==> Bouncing freya web deployment..."
kubectl --context=freya rollout restart deploy/s8njee-web -n "$FREYA_NS"
kubectl --context=freya rollout status deploy/s8njee-web -n "$FREYA_NS"

echo "==> Done. Freya DB is now a mirror of netcup."
