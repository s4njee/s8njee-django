import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blog.settings.production")

app = Celery("blog")
# namespace="CELERY" makes Django settings like CELERY_BROKER_URL configure Celery.
app.config_from_object("django.conf:settings", namespace="CELERY")
# autodiscover_tasks imports tasks.py from installed Django apps.
app.autodiscover_tasks()
