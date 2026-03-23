# s8njee-web

Single Django site for the blog and photo gallery.

- Blog lives at `/`
- Photos live at `/photos/`
- Active application code lives in `blog/`
- The old standalone `photos/` service has been archived under `archive/photos-standalone-app/`

## Prerequisites

- Docker and Docker Compose for production
- Python 3.13 and `uv` for local development
- A DNS record pointing your chosen hostname to the server
- TLS certificate and key for that hostname

## Environment Files

Copy the example files and fill in real values before deploying:

```bash
cp .env.example .env
cp blog/.env.example blog/.env
cp db.env.example db.env
```

- `.env` configures Docker Compose and nginx host-level values.
- `blog/.env` configures Django.
- `db.env` configures PostgreSQL.

Generate a Django secret key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

## Local Development

The local development path is the Django app in `blog/` with SQLite by default.

1. Copy `blog/.env.example` to `blog/.env`.
2. Leave the `DB_*` variables blank to use SQLite, or point them at a running PostgreSQL instance.
3. Start the app:

```bash
cd blog
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The site will be available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/) with photos under [http://127.0.0.1:8000/photos/](http://127.0.0.1:8000/photos/).

## Production Deployment

The production path is Docker Compose with three services: `db`, `web`, and `nginx`.

1. Copy the example env files shown above.
2. Put your TLS assets in the paths referenced by `.env`.
3. Set production values in `blog/.env`:
   - `DEBUG=False`
   - `ALLOWED_HOSTS=<your hostname>`
   - `CSRF_TRUSTED_ORIGINS=https://<your hostname>`
   - PostgreSQL credentials matching `db.env`
   - Optional S3 credentials if you want media in S3 instead of the local Docker volume
4. Build and start the stack:

```bash
docker compose up -d --build
```

`blog/start.sh` is the canonical release entrypoint. On container startup it runs migrations, loads starter content only on an empty site, collects static files, and then starts Uvicorn.

Create the admin user if needed:

```bash
docker compose exec web uv run python manage.py createsuperuser
```

## Storage Modes

- Leave the AWS variables blank to store uploaded media in the Docker `app-media` volume.
- Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, and `AWS_S3_REGION_NAME` in `blog/.env` to store uploaded media in S3.
- Static files are always collected into `app-static` for nginx to serve.

## Seed Data

- Fresh empty deployments are seeded from [`blog/fixtures/seed_content.json`](blog/fixtures/seed_content.json).
- The seed fixture contains live content for `posts.post`, `albums.album`, and `albums.photo`.
- Photo rows reference media object keys only. To render images correctly on a seeded environment, point the app at the same S3 bucket or restore the matching media files separately.

## Frontend Stack

The site uses Django templates with vanilla CSS. There is no separate Webpack or Tailwind build step.

## Updating

```bash
docker compose up -d --build
```

## Logs

```bash
docker compose logs -f
docker compose logs -f web
docker compose logs -f nginx
docker compose logs -f db
```

## Deployment Checklist

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for SSL, credentials, media storage, migrations, static collection, and admin bootstrap steps.
