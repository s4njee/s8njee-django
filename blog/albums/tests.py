import io
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Album, Photo, PhotoStatus


class PhotoUploadAsyncTests(TestCase):
    def setUp(self):
        self.staff_user = get_user_model().objects.create_user(
            username="album-editor",
            password="testpass123",
            is_staff=True,
        )
        self.album = Album.objects.create(title="Async Album")
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MEDIA_URL="/media/",
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root)

    def make_image_upload(self, name="test-image.png", image_format="PNG", content_type="image/png"):
        image_bytes = io.BytesIO()
        Image.new("RGB", (64, 64), color="red").save(image_bytes, format=image_format)
        image_bytes.seek(0)
        return SimpleUploadedFile(name, image_bytes.read(), content_type=content_type)

    def make_exif_upload(self):
        image_bytes = io.BytesIO()
        img = Image.new("RGB", (64, 64), color="blue")
        exif = Image.Exif()
        exif[271] = "NIKON CORPORATION"
        exif[272] = "NIKON D600"
        exif[36867] = "2024:01:02 03:04:05"
        exif[33434] = (1, 250)
        exif[33437] = (56, 10)
        exif[34855] = 640
        exif[37386] = (50, 1)
        img.save(image_bytes, format="JPEG", exif=exif.tobytes())
        image_bytes.seek(0)
        return SimpleUploadedFile("exif.jpg", image_bytes.read(), content_type="image/jpeg")

    def test_photo_upload_queues_pending_photo_when_async(self):
        self.client.force_login(self.staff_user)

        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
                with patch("albums.views.process_photo.delay") as delay_mock:
                    response = self.client.post(
                        reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                        {"image": self.make_image_upload("queued.png")},
                    )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], PhotoStatus.PENDING)
        self.assertIn("poll_url", payload)
        delay_mock.assert_called_once()

        photo = Photo.objects.get(pk=payload["id"])
        self.assertEqual(photo.status, PhotoStatus.PENDING)
        self.assertTrue(photo.original.name.startswith("photos/originals/"))

        status_response = self.client.get(payload["poll_url"])
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], PhotoStatus.PENDING)

    def test_photo_upload_processes_image_inline_when_celery_is_eager(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("eager.png")},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], PhotoStatus.READY)
        self.assertIn("url", payload)
        self.assertIn("thumbnail_url", payload)

        photo = Photo.objects.get(pk=payload["id"])
        self.assertEqual(photo.status, PhotoStatus.READY)
        self.assertTrue(photo.image.name.endswith(".png"))
        self.assertTrue(photo.thumbnail.name)

    def test_photo_upload_rejects_non_images(self):
        self.client.force_login(self.staff_user)
        upload = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")

        response = self.client.post(
            reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
            {"image": upload},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "The uploaded file is not a supported image.")

    def test_album_detail_renders_exif_metadata_for_ready_photo(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_exif_upload()},
            )

        self.assertEqual(response.status_code, 201)
        photo = Photo.objects.get(pk=response.json()["id"])
        self.assertEqual(photo.exif_data["Camera Make"], "NIKON CORPORATION")
        self.assertEqual(photo.exif_data["Camera Model"], "NIKON D600")

        album_response = self.client.get(reverse("album_detail", kwargs={"pk": self.album.pk}))
        self.assertContains(album_response, "EXIF")
        self.assertContains(album_response, "Camera Make")
        self.assertContains(album_response, "NIKON D600")
