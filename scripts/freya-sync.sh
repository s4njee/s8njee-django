#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DEST="${FREYA_SYNC_DEST:-freya.local:/home/sanjee/tmp/s8njee-web/blog/}"
ROLLOUT=0

for arg in "$@"; do
  case "$arg" in
    --rollout) ROLLOUT=1 ;;
  esac
done

rsync -az --delete \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude '*.pyc' \
  --exclude db.sqlite3 \
  --exclude staticfiles \
  "$ROOT_DIR/blog/" "$DEST"

if [ "$ROLLOUT" = "1" ]; then
  kubectl --context=freya rollout restart deploy/s8njee-web -n default
  kubectl --context=freya rollout status deploy/s8njee-web -n default
fi
