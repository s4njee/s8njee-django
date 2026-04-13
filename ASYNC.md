# Async Photo Upload Processing

Implementation plan for offloading the photo processing pipeline to Celery + Valkey background workers.

---

## Problem

The XHR upload endpoint (`albums/views.py:63–131`, `photo_upload_single`) currently does all heavy work synchronously inside the HTTP request:

1. **RAW branch** (`views.py:76–111`): reads entire file into memory → `rawpy.imread().postprocess()` to demosaic pixels → PIL downscale to 1920px → AVIF re-encode with EXIF reinjection.
2. **Non-RAW branch** (`views.py:114–128`): PIL open → downscale → JPEG re-encode.
3. **Thumbnail** (`models.py:43–72`): `Photo.save()` triggers `_make_thumbnail` — a second PIL open + thumbnail + encode + write to storage.

A large NEF upload can take 10–30 seconds. With only 2 uvicorn workers (`start.sh:18`) a batch upload of RAW files can lock out all web traffic. There is also no user feedback while the request hangs.

---

## Architecture

```
Browser
  │
  │  POST /albums/<pk>/upload/single/
  ▼
Django view (fast path)
  ├─ validate extension
  ├─ save raw bytes → Photo.original (S3 / local)
  ├─ insert Photo row (status=pending)
  ├─ process_photo.delay(photo.id)  ──►  Valkey broker
  └─ return 202 { id, status, poll_url }

Celery worker (separate k8s Deployment)
  ├─ pick up process_photo task from Valkey
  ├─ load Photo, open Photo.original
  ├─ run RAW/downscale/AVIF + thumbnail pipeline
  ├─ save Photo.image + Photo.thumbnail to storage
  └─ update Photo.status = ready (or failed + error)

Browser
  └─ poll GET /albums/photos/<id>/status/ every 1.5 s
     └─ on ready: replace placeholder with real thumbnail
     └─ on failed: show error message
```

**Broker**: Valkey 8 (open-source Redis fork). Celery's `redis://` transport works with Valkey unchanged.

**Result backend**: none. Status lives on the `Photo` row — no double source of truth, no django-celery-results dependency.

---

## Step-by-step implementation

### 1. Add dependency

`blog/pyproject.toml`:
```toml
dependencies = [
    ...
    "celery[redis]>=5.4",
]
```

Run `uv lock` and commit `uv.lock`.

---

### 2. Model changes — `blog/albums/models.py`

Add three fields to `Photo`:

```python
class Photo(models.Model):
    ...
    # Existing fields remain; add:
    original  = models.FileField(upload_to="photos/originals/%Y/%m/%d/", blank=True)
    status    = models.CharField(
        max_length=16,
        choices=[("pending","pending"),("processing","processing"),
                 ("ready","ready"),("failed","failed")],
        default="pending",
        db_index=True,
    )
    error     = models.TextField(blank=True)
```

Make `image` and `thumbnail` nullable so they can start empty:

```python
    image     = models.ImageField(upload_to="photos/%Y/%m/%d/", blank=True)
    thumbnail = models.ImageField(upload_to="photos/%Y/%m/%d/thumbs/", blank=True)
```

Remove the thumbnail call from `save()` — the task handles it now:

```python
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)   # no more _make_thumbnail here
```

Keep `_make_thumbnail` as a private helper so the task can call it.

**Migration**: `0002_photo_async_fields.py`. Add a data migration that backfills all existing rows to `status="ready"` so nothing breaks on deploy.

---

### 3. Celery app — `blog/blog/celery.py` (new file)

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blog.settings.production")

app = Celery("blog")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

Wire into `blog/blog/__init__.py`:

```python
from .celery import app as celery_app
__all__ = ("celery_app",)
```

---

### 4. Settings — `blog/blog/settings/base.py`

```python
CELERY_BROKER_URL          = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER   = env.bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_ACKS_LATE      = True   # re-queue on worker crash
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT     = 600    # hard kill after 10 min
CELERY_TASK_SOFT_TIME_LIMIT = 540   # SoftTimeLimitExceeded at 9 min
```

In `blog/blog/settings/development.py` override:

```python
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", True)
```

`ALWAYS_EAGER=True` means local `uv run python manage.py runserver` executes tasks inline — no Valkey/worker needed. Flip to `False` via env when you want to test the real async path locally.

---

### 5. Task — `blog/albums/tasks.py` (new file)

Move the entire processing pipeline out of the view and into a Celery task:

```python
import io
import os

from celery import shared_task
from django.core.files.base import ContentFile
from PIL import Image
import pillow_heif
import rawpy

pillow_heif.register_heif_opener()

RAW_EXTENSIONS = {'.nef', '.cr2', '.cr3', '.dng', '.arw', '.orf', '.raf', '.rw2'}
MAX_DIMENSION  = 1920


def _downscale_if_needed(img):
    w, h = img.size
    if w <= MAX_DIMENSION and h <= MAX_DIMENSION:
        return img
    scale = MAX_DIMENSION / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


@shared_task(
    bind=True,
    autoretry_for=(IOError, OSError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_photo(self, photo_id: str):
    from .models import Photo  # local import avoids circular imports at module load

    photo = Photo.objects.get(pk=photo_id)

    # Idempotency guard
    if photo.status == "ready":
        return

    photo.status = "processing"
    photo.save(update_fields=["status"])

    try:
        ext = os.path.splitext(photo.original.name)[1].lower()

        with photo.original.open("rb") as fh:
            file_bytes = fh.read()

        if ext in RAW_EXTENSIONS:
            # Rescue EXIF from TIFF header
            exif_bytes = b""
            try:
                temp_img = Image.open(io.BytesIO(file_bytes))
                if "exif" in temp_img.info:
                    exif_bytes = temp_img.info["exif"]
            except Exception:
                pass

            with rawpy.imread(io.BytesIO(file_bytes)) as raw:
                rgb = raw.postprocess()

            img = Image.fromarray(rgb)
            img = _downscale_if_needed(img)

            out_buf = io.BytesIO()
            save_kwargs = {"format": "AVIF", "quality": 85}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            img.save(out_buf, **save_kwargs)
            out_buf.seek(0)

            new_name = os.path.splitext(os.path.basename(photo.original.name))[0] + ".avif"
            processed = ContentFile(out_buf.read(), name=new_name)

        else:
            orig = Image.open(io.BytesIO(file_bytes))
            resized = _downscale_if_needed(orig)
            if resized is not orig:
                out_buf = io.BytesIO()
                fmt = orig.format or "JPEG"
                save_kwargs = {"format": fmt}
                if fmt == "JPEG":
                    save_kwargs["quality"] = 85
                resized.save(out_buf, **save_kwargs)
                out_buf.seek(0)
                processed = ContentFile(out_buf.read(), name=os.path.basename(photo.original.name))
            else:
                processed = ContentFile(file_bytes, name=os.path.basename(photo.original.name))

        photo.image.save(processed.name, processed, save=False)
        photo._make_thumbnail()
        photo.status = "ready"
        photo.save(update_fields=["image", "thumbnail", "status"])

        # Optional: delete original to save storage
        # photo.original.delete(save=False)

    except Exception as exc:
        photo.status = "failed"
        photo.error = str(exc)[:2000]
        photo.save(update_fields=["status", "error"])
        raise  # re-raise so Celery retries
```

---

### 6. View refactor — `blog/albums/views.py`

Replace the heavy `photo_upload_single` with a fast path:

```python
from django.urls import reverse
from .tasks import process_photo

@login_required
def photo_upload_single(request, album_pk):
    album = get_object_or_404(Album, pk=album_pk)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image provided"}, status=400)

    # Validate extension (reuse existing form validator)
    from .forms import ACCEPTED_EXTENSIONS
    ext = os.path.splitext(image.name)[1].lower()
    if ext not in ACCEPTED_EXTENSIONS:
        return JsonResponse({"error": f"Unsupported file type: {ext}"}, status=400)

    photo = Photo.objects.create(album=album, original=image)
    process_photo.delay(str(photo.pk))

    return JsonResponse({
        "id": str(photo.pk),
        "status": "pending",
        "poll_url": reverse("photo_status", args=[photo.pk]),
    }, status=202)
```

Remove `import rawpy`, `import pillow_heif`, `_downscale_if_needed`, and `RAW_EXTENSIONS` from this file — they now live in `tasks.py`.

Add a new status endpoint:

```python
def photo_status(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    data = {"id": str(photo.pk), "status": photo.status}
    if photo.status == "ready":
        data["image_url"]     = photo.image.url
        data["thumbnail_url"] = photo.thumbnail.url
    elif photo.status == "failed":
        data["error"] = photo.error
    return JsonResponse(data)
```

Wire it in `albums/urls.py`:
```python
path("photos/<uuid:pk>/status/", views.photo_status, name="photo_status"),
```

---

### 7. Frontend — `blog/albums/templates/albums/photo_upload.html`

Update the JS that handles the XHR response. On a `202` response, insert a "processing" placeholder and poll:

```javascript
async function pollStatus(pollUrl, placeholderEl) {
    const MAX = 120;
    for (let i = 0; i < MAX; i++) {
        await new Promise(r => setTimeout(r, 1500));
        const res = await fetch(pollUrl);
        const data = await res.json();
        if (data.status === "ready") {
            placeholderEl.innerHTML = `<img src="${data.thumbnail_url}" alt="">`;
            return;
        }
        if (data.status === "failed") {
            placeholderEl.innerHTML = `<span class="error">Failed: ${data.error}</span>`;
            return;
        }
    }
    placeholderEl.innerHTML = `<span class="error">Timed out waiting for processing</span>`;
}

// In the existing upload handler, replace the success branch:
if (res.status === 202) {
    const data = await res.json();
    const placeholder = insertPlaceholderCard();  // add a spinner card to the grid
    pollStatus(data.poll_url, placeholder);
}
```

No framework needed — plain `fetch()`. The placeholder card can be a simple spinner in the existing gallery grid style.

---

### 8. Valkey in Kubernetes — `k8s/base/`

**`k8s/base/valkey-deployment.yaml`** (new):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: valkey
spec:
  replicas: 1
  selector:
    matchLabels: {app: valkey}
  template:
    metadata:
      labels: {app: valkey}
    spec:
      containers:
        - name: valkey
          image: valkey/valkey:8-alpine
          args: ["valkey-server", "--appendonly", "no"]
          ports:
            - containerPort: 6379
          resources:
            requests: {memory: "64Mi", cpu: "50m"}
            limits:   {memory: "256Mi", cpu: "200m"}
```

**`k8s/base/valkey-service.yaml`** (new):
```yaml
apiVersion: v1
kind: Service
metadata:
  name: valkey
spec:
  selector: {app: valkey}
  ports:
    - port: 6379
      targetPort: 6379
```

**`k8s/base/celery-worker-deployment.yaml`** (new):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: s8njee-celery-worker
spec:
  replicas: 1
  selector:
    matchLabels: {app: s8njee-celery-worker}
  template:
    metadata:
      labels: {app: s8njee-celery-worker}
    spec:
      containers:
        - name: worker
          image: registry.s8njee.com/s8njee-web:latest  # same image as web
          command: ["uv", "run", "celery", "-A", "blog", "worker",
                    "-l", "info", "--concurrency=2"]
          envFrom:
            - configMapRef: {name: s8njee-config}
            - secretRef:    {name: s8njee-secret}
          env:
            - name: CELERY_BROKER_URL
              value: "redis://valkey:6379/0"
          resources:
            requests: {memory: "256Mi", cpu: "100m"}
            limits:   {memory: "1Gi",   cpu: "1000m"}
```

Add all three new files to `k8s/base/kustomization.yaml` under `resources:`.

Add `CELERY_BROKER_URL: redis://valkey:6379/0` to the web Deployment's env in `k8s/overlays/netcup/configmap.yaml` (or deployment patch).

The web Deployment stays pinned at 1 replica for migrations. The worker Deployment is independent and can scale separately.

---

### 9. Docker Compose — `docker-compose.yml`

Add to the existing compose file:

```yaml
services:
  ...
  valkey:
    image: valkey/valkey:8-alpine
    ports:
      - "6379:6379"
    command: valkey-server --appendonly no

  celery:
    build: ./blog
    command: uv run celery -A blog worker -l info
    depends_on:
      - valkey
      - db
    env_file: .env
    environment:
      CELERY_BROKER_URL: "redis://valkey:6379/0"
      CELERY_TASK_ALWAYS_EAGER: "False"
    volumes:
      - app-media:/app/media
```

For local `uv run python manage.py runserver` development, `CELERY_TASK_ALWAYS_EAGER` defaults to `True` (set in `settings/development.py`), so no Valkey or worker is needed unless you're specifically testing the async path.

---

## Rollout checklist

1. [ ] Add `celery[redis]>=5.4` to `blog/pyproject.toml`, run `uv lock`.
2. [ ] Create `blog/blog/celery.py` and update `blog/blog/__init__.py`.
3. [ ] Add Celery settings to `base.py`; set `ALWAYS_EAGER=True` default in `development.py`.
4. [ ] Add `original`, `status`, `error` fields to `Photo`; make `image`/`thumbnail` blank; strip `_make_thumbnail` call from `Photo.save()`.
5. [ ] `uv run python manage.py makemigrations && migrate`. Write data migration to backfill `status="ready"` on existing rows.
6. [ ] Create `blog/albums/tasks.py` with `process_photo`.
7. [ ] Refactor `photo_upload_single`; add `photo_status` view + URL.
8. [ ] Update frontend JS for 202 response + polling.
9. [ ] Test locally with `ALWAYS_EAGER=True` — full pipeline runs synchronously through task code.
10. [ ] Start `docker compose up valkey celery`, set `CELERY_TASK_ALWAYS_EAGER=False`, test real async path — upload a NEF, watch worker logs, confirm photo transitions to `ready`.
11. [ ] Add k8s manifests (`valkey-deployment.yaml`, `valkey-service.yaml`, `celery-worker-deployment.yaml`); update `kustomization.yaml`.
12. [ ] Add `CELERY_BROKER_URL` to netcup ConfigMap / sealed secret.
13. [ ] Argo CD sync. Confirm Valkey pod runs, worker connects, end-to-end upload works.

---

## Verification

| Test | How |
|------|-----|
| Unit | `pytest` with `CELERY_TASK_ALWAYS_EAGER=True` — call `process_photo` with a JPEG and a NEF fixture; assert `Photo.status == "ready"`, `photo.image` and `photo.thumbnail` are populated. |
| Integration | `docker compose up`, upload via browser, watch `docker compose logs celery`, confirm 202 → polling → thumbnail appears. |
| Failure path | Upload a zero-byte `.nef`; assert `Photo.status == "failed"`, `photo.error` is non-empty, retry count increments. |
| Production smoke | After deploy: `kubectl logs deploy/s8njee-celery-worker -f`, upload one JPEG + one NEF to a test album, confirm status transitions in Django admin. |

---

## Non-goals / deferred

- **Celery Beat** — no periodic tasks needed yet.
- **Flower** monitoring dashboard — can add as a separate Deployment later.
- **WebSockets / SSE** — polling at 1.5 s is sufficient; no real-time infra needed.
- **django-celery-results** — status on the Photo model is simpler and avoids a second data store.
- **Sync fallback** — if Valkey is down, uploads stay `pending`. This is intentional; the status endpoint surfaces the problem clearly.
- **Rate limiting / quotas** — out of scope.
- **Celery result TTL / cleanup** — no result backend means no cleanup needed.
