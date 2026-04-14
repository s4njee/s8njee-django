#!/bin/sh
set -eu

# Prefer the in-cluster service environment variables when Kubernetes injects them.
# This keeps startup working even if DNS lookups for the service name are broken.
DB_HOST="${S8NJEE_POSTGRES_SERVICE_HOST:-${DB_HOST:-}}"
DB_PORT="${S8NJEE_POSTGRES_SERVICE_PORT:-${DB_PORT:-5432}}"
export DB_HOST DB_PORT
export DJANGO_SETTINGS_MODULE=blog.settings.production

uv run python manage.py migrate --noinput
if uv run python manage.py shell -c "from posts.models import Post; from albums.models import Album; raise SystemExit(0 if Post.objects.exists() or Album.objects.exists() else 1)"; then
  :
else
  uv run python manage.py loaddata fixtures/seed_content.json
fi
uv run python manage.py backfill_photo_sort_order
uv run python manage.py collectstatic --noinput
exec uv run uvicorn blog.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --lifespan off
