#!/usr/bin/env bash
# Mirror the production netcup PostgreSQL database into the Freya PostgreSQL
# database. This is intentionally destructive for Freya only.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

NETCUP_CONTEXT="${NETCUP_CONTEXT:-netcup}"
NETCUP_NS="${NETCUP_NS:-s8njee-web}"
NETCUP_POSTGRES_LABEL="${NETCUP_POSTGRES_LABEL:-app=s8njee-postgres}"
NETCUP_POD="${NETCUP_POD:-}"

FREYA_CONTEXT="${FREYA_CONTEXT:-freya}"
FREYA_NS="${FREYA_NS:-default}"
FREYA_POSTGRES_LABEL="${FREYA_POSTGRES_LABEL:-app=s8njee-postgres}"
FREYA_POD="${FREYA_POD:-}"
FREYA_STOP_DEPLOYS="${FREYA_STOP_DEPLOYS:-s8njee-web s8njee-celery-worker}"

BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
NETCUP_DUMP=""
FREYA_DUMP=""

YES=0
DRY_RUN=0
BACKUP_FREYA=1
STOP_FREYA_WORKLOADS=1
WAIT_ROLLOUT=1

ORIGINAL_DEPLOYS=()
ORIGINAL_REPLICAS=()
SCALED_DOWN=0

usage() {
  cat <<'EOF'
Usage:
  scripts/netcup-to-freya-db-sync.sh [options]

Mirrors the production netcup PostgreSQL database into the Freya PostgreSQL
database. This overwrites Freya's database after saving dumps under backups/.

Options:
  -y, --yes                 Skip the destructive confirmation prompt.
      --dry-run             Validate contexts/pods and print planned actions.
      --skip-freya-backup   Do not dump Freya before overwriting it.
      --no-stop-workloads   Do not scale Freya web/celery down during restore.
      --skip-rollout-wait   Do not wait for Freya deployments after restore.
      --backup-dir PATH     Directory for local dump files.
      --netcup-context CTX  Kubernetes context for production netcup.
      --netcup-namespace NS Kubernetes namespace for production netcup.
      --netcup-pod POD      Explicit production PostgreSQL pod name.
      --freya-context CTX   Kubernetes context for Freya.
      --freya-namespace NS  Kubernetes namespace for Freya.
      --freya-pod POD       Explicit Freya PostgreSQL pod name.
  -h, --help                Show this help.

Environment overrides:
  NETCUP_CONTEXT, NETCUP_NS, NETCUP_POSTGRES_LABEL, NETCUP_POD
  FREYA_CONTEXT, FREYA_NS, FREYA_POSTGRES_LABEL, FREYA_POD
  FREYA_STOP_DEPLOYS, BACKUP_DIR

Examples:
  scripts/netcup-to-freya-db-sync.sh
  scripts/netcup-to-freya-db-sync.sh --yes
  scripts/netcup-to-freya-db-sync.sh --dry-run
EOF
}

log() {
  printf '==> %s\n' "$*"
}

note() {
  printf '    %s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

kubectl_ctx() {
  local context="$1"
  shift
  kubectl --context "$context" "$@"
}

find_postgres_pod() {
  local context="$1"
  local namespace="$2"
  local label="$3"
  local explicit_pod="$4"

  if [[ -n "$explicit_pod" ]]; then
    printf '%s\n' "$explicit_pod"
    return
  fi

  kubectl_ctx "$context" get pod \
    -n "$namespace" \
    -l "$label" \
    --field-selector=status.phase=Running \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
    | head -n 1
}

postgres_exec() {
  local context="$1"
  local namespace="$2"
  local pod="$3"
  local command="$4"

  kubectl_ctx "$context" exec -n "$namespace" "$pod" -- sh -lc "$command"
}

dump_postgres() {
  local context="$1"
  local namespace="$2"
  local pod="$3"
  local output_file="$4"
  local tmp_file="$output_file.tmp"

  rm -f "$tmp_file"
  kubectl_ctx "$context" exec -n "$namespace" "$pod" -- \
    sh -lc 'PGPASSWORD="${POSTGRES_PASSWORD:?}" pg_dump -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" --no-owner --no-privileges' \
    | gzip -c > "$tmp_file"
  mv "$tmp_file" "$output_file"
}

restore_postgres() {
  local context="$1"
  local namespace="$2"
  local pod="$3"
  local input_file="$4"

  postgres_exec "$context" "$namespace" "$pod" \
    'PGPASSWORD="${POSTGRES_PASSWORD:?}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;"'

  gunzip -c "$input_file" | kubectl_ctx "$context" exec -i -n "$namespace" "$pod" -- \
    sh -lc 'PGPASSWORD="${POSTGRES_PASSWORD:?}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" -q'

  postgres_exec "$context" "$namespace" "$pod" \
    'PGPASSWORD="${POSTGRES_PASSWORD:?}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" -c "VACUUM ANALYZE;"'
}

verify_postgres() {
  local context="$1"
  local namespace="$2"
  local pod="$3"

  postgres_exec "$context" "$namespace" "$pod" \
    'PGPASSWORD="${POSTGRES_PASSWORD:?}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" -Atc "
select '\''django_migrations='\'' || count(*) from django_migrations;
select '\''posts_post='\'' || count(*) from posts_post;
select '\''albums_album='\'' || count(*) from albums_album;
select '\''albums_photo='\'' || count(*) from albums_photo;
"'
}

deployment_exists() {
  local deploy="$1"
  kubectl_ctx "$FREYA_CONTEXT" get deploy "$deploy" -n "$FREYA_NS" >/dev/null 2>&1
}

scale_freya_down() {
  [[ "$STOP_FREYA_WORKLOADS" -eq 1 ]] || return

  log "Scaling Freya workloads down before restore..."
  for deploy in $FREYA_STOP_DEPLOYS; do
    if deployment_exists "$deploy"; then
      local replicas
      replicas="$(kubectl_ctx "$FREYA_CONTEXT" get deploy "$deploy" -n "$FREYA_NS" -o jsonpath='{.spec.replicas}')"
      [[ -n "$replicas" ]] || replicas=1
      ORIGINAL_DEPLOYS+=("$deploy")
      ORIGINAL_REPLICAS+=("$replicas")
      note "$deploy: $replicas -> 0"
      run kubectl_ctx "$FREYA_CONTEXT" scale deploy "$deploy" -n "$FREYA_NS" --replicas=0
    else
      note "$deploy: not found, skipping"
    fi
  done
  SCALED_DOWN=1
}

scale_freya_up() {
  [[ "$SCALED_DOWN" -eq 1 ]] || return

  log "Scaling Freya workloads back up..."
  local index
  for index in "${!ORIGINAL_DEPLOYS[@]}"; do
    local deploy="${ORIGINAL_DEPLOYS[$index]}"
    local replicas="${ORIGINAL_REPLICAS[$index]}"
    note "$deploy: 0 -> $replicas"
    run kubectl_ctx "$FREYA_CONTEXT" scale deploy "$deploy" -n "$FREYA_NS" --replicas="$replicas"
  done

  if [[ "$DRY_RUN" -eq 0 && "$WAIT_ROLLOUT" -eq 1 ]]; then
    for deploy in "${ORIGINAL_DEPLOYS[@]}"; do
      kubectl_ctx "$FREYA_CONTEXT" rollout status deploy "$deploy" -n "$FREYA_NS"
    done
  fi

  SCALED_DOWN=0
}

cleanup_on_exit() {
  local status=$?
  if [[ "$status" -ne 0 && "$SCALED_DOWN" -eq 1 ]]; then
    printf 'ERROR: sync failed; attempting to restore Freya deployment replicas\n' >&2
    scale_freya_up || true
  fi
}

confirm_destructive_restore() {
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi

  printf '\n'
  printf 'This will overwrite the Freya PostgreSQL database with production netcup data.\n'
  printf 'Netcup source: %s/%s\n' "$NETCUP_CONTEXT" "$NETCUP_NS"
  printf 'Freya target:  %s/%s\n' "$FREYA_CONTEXT" "$FREYA_NS"
  printf 'Type "sync freya from netcup" to continue: '

  local reply
  IFS= read -r reply
  [[ "$reply" == "sync freya from netcup" ]] || die "confirmation did not match"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)
      YES=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --skip-freya-backup)
      BACKUP_FREYA=0
      shift
      ;;
    --no-stop-workloads)
      STOP_FREYA_WORKLOADS=0
      shift
      ;;
    --skip-rollout-wait)
      WAIT_ROLLOUT=0
      shift
      ;;
    --backup-dir)
      BACKUP_DIR="${2:?--backup-dir requires a path}"
      shift 2
      ;;
    --netcup-context)
      NETCUP_CONTEXT="${2:?--netcup-context requires a value}"
      shift 2
      ;;
    --netcup-namespace)
      NETCUP_NS="${2:?--netcup-namespace requires a value}"
      shift 2
      ;;
    --netcup-pod)
      NETCUP_POD="${2:?--netcup-pod requires a value}"
      shift 2
      ;;
    --freya-context)
      FREYA_CONTEXT="${2:?--freya-context requires a value}"
      shift 2
      ;;
    --freya-namespace)
      FREYA_NS="${2:?--freya-namespace requires a value}"
      shift 2
      ;;
    --freya-pod)
      FREYA_POD="${2:?--freya-pod requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

trap cleanup_on_exit EXIT

require_command kubectl
require_command gzip
require_command gunzip

NETCUP_DUMP="$BACKUP_DIR/netcup-$STAMP.sql.gz"
FREYA_DUMP="$BACKUP_DIR/freya-before-netcup-sync-$STAMP.sql.gz"

if [[ "$DRY_RUN" -eq 0 ]]; then
  mkdir -p "$BACKUP_DIR"
fi

log "Locating PostgreSQL pods..."
NETCUP_POD="$(find_postgres_pod "$NETCUP_CONTEXT" "$NETCUP_NS" "$NETCUP_POSTGRES_LABEL" "$NETCUP_POD")"
FREYA_POD="$(find_postgres_pod "$FREYA_CONTEXT" "$FREYA_NS" "$FREYA_POSTGRES_LABEL" "$FREYA_POD")"
[[ -n "$NETCUP_POD" ]] || die "could not find running netcup PostgreSQL pod"
[[ -n "$FREYA_POD" ]] || die "could not find running Freya PostgreSQL pod"
note "netcup: $NETCUP_POD"
note "freya:  $FREYA_POD"

log "Checking PostgreSQL connectivity..."
postgres_exec "$NETCUP_CONTEXT" "$NETCUP_NS" "$NETCUP_POD" \
  'PGPASSWORD="${POSTGRES_PASSWORD:?}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" -Atc "select current_database() || '\'' as '\'' || current_user;"'
postgres_exec "$FREYA_CONTEXT" "$FREYA_NS" "$FREYA_POD" \
  'PGPASSWORD="${POSTGRES_PASSWORD:?}" psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" -Atc "select current_database() || '\'' as '\'' || current_user;"'

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "Dry run complete. No dumps or restores were performed."
  exit 0
fi

confirm_destructive_restore

log "Dumping production netcup database..."
dump_postgres "$NETCUP_CONTEXT" "$NETCUP_NS" "$NETCUP_POD" "$NETCUP_DUMP"
note "saved: $NETCUP_DUMP"

if [[ "$BACKUP_FREYA" -eq 1 ]]; then
  log "Backing up current Freya database before overwrite..."
  dump_postgres "$FREYA_CONTEXT" "$FREYA_NS" "$FREYA_POD" "$FREYA_DUMP"
  note "saved: $FREYA_DUMP"
fi

scale_freya_down

log "Restoring netcup dump into Freya..."
restore_postgres "$FREYA_CONTEXT" "$FREYA_NS" "$FREYA_POD" "$NETCUP_DUMP"

log "Verifying Freya row counts..."
verify_postgres "$FREYA_CONTEXT" "$FREYA_NS" "$FREYA_POD"

scale_freya_up

log "Done. Freya PostgreSQL now mirrors production netcup content."
