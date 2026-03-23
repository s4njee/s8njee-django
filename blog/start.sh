#!/bin/sh
set -eu

uv run python manage.py migrate --noinput
if uv run python manage.py shell -c "from posts.models import Post; from albums.models import Album; raise SystemExit(0 if Post.objects.exists() or Album.objects.exists() else 1)"; then
  :
else
  uv run python manage.py loaddata fixtures/seed_content.json
fi
uv run python manage.py collectstatic --noinput
exec uv run uvicorn blog.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --lifespan off
