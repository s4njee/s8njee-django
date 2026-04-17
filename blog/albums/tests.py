import os
import json
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

    def test_album_detail_exposes_photo_permalink_for_lightbox_navigation(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            upload_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("permalink.png")},
            )

        photo = Photo.objects.get(pk=upload_response.json()["id"])
        album_response = self.client.get(reverse("album_detail", kwargs={"pk": self.album.pk}))

        self.assertContains(
            album_response,
            f'data-photo-url="{reverse("photo_permalink", kwargs={"album_pk": self.album.pk, "photo_pk": photo.pk})}"',
            html=False,
        )

    def test_photo_permalink_returns_lightbox_fragment_for_htmx_requests(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            first_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("lightbox-a.png")},
            )

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            second_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("lightbox-b.png")},
            )

        photo = Photo.objects.get(pk=first_response.json()["id"])

        response = self.client.get(
            reverse("photo_permalink", kwargs={"album_pk": self.album.pk, "photo_pk": photo.pk}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="lightbox-shell"', html=False)
        self.assertContains(response, 'hx-push-url="true"', html=False)
        self.assertContains(response, 'hx-get=', html=False)
        self.assertContains(response, str(photo.pk), html=False)

        redirect_response = self.client.get(
            reverse("photo_permalink", kwargs={"album_pk": self.album.pk, "photo_pk": photo.pk})
        )
        self.assertEqual(redirect_response.status_code, 302)
        self.assertEqual(
            redirect_response.url,
            f"{reverse('album_detail', kwargs={'pk': self.album.pk})}#photo-{photo.pk}",
        )

    def test_nonstaff_cannot_open_album_creation(self):
        regular_user = get_user_model().objects.create_user(
            username="album-viewer",
            password="testpass123",
        )
        self.client.force_login(regular_user)

        response = self.client.get(reverse("album_create"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_edit_album_metadata(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("album_edit", kwargs={"pk": self.album.pk}),
            {"title": "Renamed Album", "description": "Updated description"},
        )

        self.assertRedirects(response, reverse("album_detail", kwargs={"pk": self.album.pk}))
        self.album.refresh_from_db()
        self.assertEqual(self.album.title, "Renamed Album")
        self.assertEqual(self.album.description, "Updated description")

    def test_staff_can_save_multiple_albums_without_slugs(self):
        self.client.force_login(self.staff_user)

        first_response = self.client.post(
            reverse("album_create"),
            {"title": "First Album", "slug": "", "description": ""},
        )
        second_response = self.client.post(
            reverse("album_create"),
            {"title": "Second Album", "slug": "", "description": ""},
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertIsNone(Album.objects.get(title="First Album").slug)
        self.assertIsNone(Album.objects.get(title="Second Album").slug)

    def test_staff_can_choose_album_cover_photo(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            first_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("cover-a.png")},
            )

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            second_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("cover-b.png")},
            )

        first_photo = Photo.objects.get(pk=first_response.json()["id"])
        second_photo = Photo.objects.get(pk=second_response.json()["id"])

        response = self.client.post(
            reverse("album_edit", kwargs={"pk": self.album.pk}),
            {
                "title": self.album.title,
                "description": self.album.description,
                "cover_photo": str(second_photo.pk),
            },
        )

        self.assertRedirects(response, reverse("album_detail", kwargs={"pk": self.album.pk}))
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover_photo_id, second_photo.pk)

        list_response = self.client.get(reverse("album_list"))
        self.assertContains(list_response, second_photo.thumbnail.url)
        self.assertNotContains(list_response, first_photo.thumbnail.url)

    def test_staff_can_set_album_cover_from_photo_card(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            upload_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("cover-card.png")},
            )

        photo = Photo.objects.get(pk=upload_response.json()["id"])
        response = self.client.post(
            reverse("album_set_cover_photo", kwargs={"album_pk": self.album.pk, "photo_pk": photo.pk})
        )

        self.assertRedirects(response, reverse("album_detail", kwargs={"pk": self.album.pk}))
        self.album.refresh_from_db()
        self.assertEqual(self.album.cover_photo_id, photo.pk)

    def test_pending_photos_do_not_offer_cover_action(self):
        self.client.force_login(self.staff_user)
        Photo.objects.create(album=self.album, status=PhotoStatus.PENDING)

        response = self.client.get(reverse("album_detail", kwargs={"pk": self.album.pk}))

        self.assertNotContains(response, "Set as Album Cover")

    def test_album_images_have_non_empty_alt_fallback(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("no-alt.png")},
            )

        detail_response = self.client.get(reverse("album_detail", kwargs={"pk": self.album.pk}))
        list_response = self.client.get(reverse("album_list"))

        self.assertContains(detail_response, 'alt="Async Album"', html=False)
        self.assertContains(list_response, 'alt="Async Album"', html=False)

    def test_staff_can_delete_album_and_album_photos(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            upload_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("delete-me.png")},
            )

        photo = Photo.objects.get(pk=upload_response.json()["id"])
        image_path = photo.image.name
        thumbnail_path = photo.thumbnail.name

        response = self.client.post(
            reverse("album_delete", kwargs={"pk": self.album.pk}),
            {"confirm": "on"},
        )

        self.assertRedirects(response, reverse("album_list"))
        self.assertFalse(Album.objects.filter(pk=self.album.pk).exists())
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())
        self.assertFalse(os.path.exists(os.path.join(self.media_root, image_path)))
        self.assertFalse(os.path.exists(os.path.join(self.media_root, thumbnail_path)))

    def test_staff_can_replace_photo_image_and_caption(self):
        self.client.force_login(self.staff_user)

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            upload_response = self.client.post(
                reverse("photo_upload_single", kwargs={"album_pk": self.album.pk}),
                {"image": self.make_image_upload("original.png", content_type="image/png")},
            )

        photo = Photo.objects.get(pk=upload_response.json()["id"])
        old_image = photo.image.name

        with patch("albums.views.transaction.on_commit", side_effect=lambda func: func()):
            response = self.client.post(
                reverse(
                    "photo_edit",
                    kwargs={"album_pk": self.album.pk, "photo_pk": photo.pk},
                ),
                {
                    "caption": "Updated caption",
                    "replace_image": self.make_image_upload("replacement.png"),
                },
            )

        self.assertRedirects(response, reverse("album_detail", kwargs={"pk": self.album.pk}))
        photo.refresh_from_db()
        self.assertEqual(photo.caption, "Updated caption")
        self.assertEqual(photo.status, PhotoStatus.READY)
        self.assertFalse(photo.original.name)
        self.assertFalse(os.path.exists(os.path.join(self.media_root, old_image)))
        self.assertTrue(photo.thumbnail.name)
        self.assertTrue(os.path.exists(os.path.join(self.media_root, photo.thumbnail.name)))

    def test_staff_can_reorder_photos_with_drag_and_drop(self):
        self.client.force_login(self.staff_user)

        first = Photo.objects.create(album=self.album, caption="First", sort_order=0)
        second = Photo.objects.create(album=self.album, caption="Second", sort_order=1)

        album_response = self.client.get(reverse("album_detail", kwargs={"pk": self.album.pk}))
        self.assertContains(album_response, 'draggable="true"', html=False)

        response = self.client.post(
            reverse("photo_reorder", kwargs={"album_pk": self.album.pk}),
            data=json.dumps(
                {
                    "ordered_photo_ids": [
                        str(second.pk),
                        str(first.pk),
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.sort_order, 1)
        self.assertEqual(second.sort_order, 0)
