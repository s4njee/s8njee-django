import logging
from pathlib import Path

from celery import shared_task
from django.core.files.base import ContentFile

from .image_processing import extract_exif_summary, make_thumbnail_from_image_file, process_uploaded_image
from .models import Photo, PhotoStatus

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(OSError, IOError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_photo(self, photo_id: str):
    photo = Photo.objects.get(pk=photo_id)

    if photo.status == PhotoStatus.READY:
        return

    photo.status = PhotoStatus.PROCESSING
    photo.error = ""
    photo.save(update_fields=["status", "error"])

    try:
        with photo.original.open("rb") as fh:
            file_bytes = fh.read()

        original_name = photo.original.name or f"{photo.id}"
        photo.exif_data = extract_exif_summary(file_bytes)
        processed = process_uploaded_image(original_name, file_bytes)
        photo.image.save(processed.name, processed, save=False)

        thumb_name, thumb_bytes = make_thumbnail_from_image_file(photo.image, str(photo.id))
        photo.thumbnail.save(thumb_name, ContentFile(thumb_bytes), save=False)

        photo.status = PhotoStatus.READY
        photo.error = ""
        photo.save(update_fields=["image", "thumbnail", "exif_data", "status", "error"])

        # Delete the staging original from storage now that processing is complete.
        # This is especially important for large RAW files (NEF, CR2, etc.).
        if photo.original:
            original_name = photo.original.name
            try:
                photo.original.delete(save=False)
                photo.original = None
                photo.save(update_fields=["original"])
                logger.info("Deleted original %s for photo %s", original_name, photo_id)
            except Exception:
                logger.exception("Failed to delete original %s for photo %s", original_name, photo_id)

        logger.info("Processed photo %s", photo_id)
    except Exception as exc:
        photo.status = PhotoStatus.FAILED
        photo.error = str(exc)[:2000]
        photo.save(update_fields=["status", "error"])
        logger.exception("Failed to process photo %s", photo_id)
        raise
