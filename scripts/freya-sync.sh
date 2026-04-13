#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DEST="${FREYA_SYNC_DEST:-freya.local:/home/sanjee/tmp/s8njee-web/blog/}"

rsync -az --delete \
  --exclude .venv \
  --exclude __pycache__ \
  --exclude '*.pyc' \
  --exclude db.sqlite3 \
  --exclude staticfiles \
  "$ROOT_DIR/blog/" "$DEST"

