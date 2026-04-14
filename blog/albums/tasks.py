import logging
from pathlib import Path

from celery import shared_task
from django.core.files.base import ContentFile

from .image_processing import extract_exif_summary, make_image_variant, make_thumbnail_from_image_file, process_uploaded_image
from .models import Photo, PhotoStatus

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(OSError, IOError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_photo(self, photo_id: str):
    # Celery task arguments should be primitive IDs; the ORM fetches fresh state.
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
        # FieldFile.save(..., save=False) stores bytes without saving the model row yet.
        photo.image.save(processed.name, processed, save=False)

        # Read the saved full-size image once; reuse bytes for all variants.
        with photo.image.open("rb") as fh:
            full_bytes = fh.read()
        full_name = photo.image.name

        for max_dim, suffix, attr in [
            (1200, "1200", "image_medium"),
            (800, "800", "image_small"),
        ]:
            variant_name, variant_bytes = make_image_variant(full_bytes, full_name, max_dim, str(photo.id), suffix)
            getattr(photo, attr).save(variant_name, ContentFile(variant_bytes), save=False)

        thumb_name, thumb_bytes = make_thumbnail_from_image_file(photo.image, str(photo.id))
        photo.thumbnail.save(thumb_name, ContentFile(thumb_bytes), save=False)

        photo.status = PhotoStatus.READY
        photo.error = ""
        # update_fields keeps this ORM write scoped to fields changed by processing.
        photo.save(update_fields=["image", "image_medium", "image_small", "thumbnail", "exif_data", "status", "error"])

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
