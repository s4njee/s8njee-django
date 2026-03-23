# Deployment Checklist

Use this checklist before each production release of the single Django site.

## 1. Provision Secrets And Env Files

- Copy `.env.example` to `.env` and set the public hostname.
- Copy `blog/.env.example` to `blog/.env` and fill in `SECRET_KEY`, hostnames, DB settings, and optional S3 settings.
- Copy `db.env.example` to `db.env` and choose a new PostgreSQL password.
- Rotate any credentials that were ever committed to the repo before reusing this deployment.

## 2. Install TLS Assets

- Place the Cloudflare origin certificate at the path configured by `SSL_CERT_PATH`.
- Place the private key at the path configured by `SSL_KEY_PATH`.
- Confirm the hostname in `.env` matches the certificate coverage.

## 3. Confirm Data Services

- Create or restore the PostgreSQL database configured in `db.env`.
- Decide on media storage mode:
  - Leave AWS variables blank to store uploaded media in the Docker `app-media` volume.
  - Set the AWS variables in `blog/.env` to store uploaded media in S3.
- If using S3, verify the bucket exists and the IAM user has read/write access.

## 4. Deploy The Release

- Run `docker compose up -d --build`.
- Confirm the `web` container completes startup successfully.
- `blog/start.sh` runs these release steps automatically:
  - `python manage.py migrate --noinput`
  - fixture load on an empty site
  - `python manage.py collectstatic --noinput`

## 5. Bootstrap Admin Access

- Create the admin user if one does not already exist:
  - `docker compose exec web uv run python manage.py createsuperuser`
- Log into `/admin/` and confirm blog posts, albums, and photo uploads are available.

## 6. Post-Deploy Smoke Check

- Open `/` and verify the blog index loads.
- Open `/photos/` and verify the gallery loads.
- Visit `/admin/login/` and confirm the login form renders over HTTPS.
- Upload a test image and confirm it lands in local media storage or S3, depending on the configured mode.
- Run `docker compose logs --tail=100 web nginx db` and confirm there are no startup errors.
