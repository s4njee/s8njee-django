from .base import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

if SECRET_KEY == 'local-dev-insecure-secret-key':
    raise ImproperlyConfigured('Set SECRET_KEY in environment before running with DEBUG=False.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

# DATABASES is consumed by Django's ORM, migrations, and management commands.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT'),
    }
}

# These settings are Django's built-in HTTPS/cookie hardening switches.
if env_bool('ENABLE_SSL', False):
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
