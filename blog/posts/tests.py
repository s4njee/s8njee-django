import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import Post


class PostMarkdownRenderingTests(TestCase):
    def test_detail_page_renders_markdown_and_strips_scripts(self):
        post = Post.objects.create(
            title='Markdown Post',
            slug='markdown-post',
            content='# Intro\n\nThis is **bold**.\n\n<script>alert("x")</script>',
            published=True,
        )

        response = self.client.get(reverse('post_detail', kwargs={'slug': post.slug}))

        self.assertContains(response, '<strong>bold</strong>', html=True)
        self.assertContains(response, '<h1>Intro</h1>', html=True)
        self.assertNotContains(response, '<script>')
        self.assertNotContains(response, 'alert("x")')

    def test_list_page_renders_markdown_preview(self):
        Post.objects.create(
            title='List Preview',
            slug='list-preview',
            content='A paragraph with `code` and a [link](https://example.com).',
            published=True,
        )

        response = self.client.get(reverse('post_list'))

        self.assertContains(response, '<code>code</code>', html=True)
        self.assertContains(
            response,
            '<a href="https://example.com" rel="noopener noreferrer">link</a>',
            html=True,
        )


class PostEditorTests(TestCase):
    def setUp(self):
        self.staff_user = get_user_model().objects.create_user(
            username="editor",
            password="testpass123",
            is_staff=True,
        )
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
        Image.new("RGB", (16, 16), color="red").save(image_bytes, format=image_format)
        image_bytes.seek(0)
        return SimpleUploadedFile(name, image_bytes.read(), content_type=content_type)

    def test_editor_requires_login(self):
        response = self.client.get(reverse("post_editor_new"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_create_post_from_editor(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("post_editor_new"),
            {
                "title": "Editor Post",
                "slug": "",
                "content": "# Hello\n\nThis came from the editor.",
                "published": "on",
            },
        )

        post = Post.objects.get(title="Editor Post")
        self.assertRedirects(response, f"{post.get_editor_url()}?saved=1")
        self.assertEqual(post.slug, "editor-post")
        self.assertTrue(post.published)

    def test_staff_editor_page_loads_toast_ui_shell(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("post_editor_new"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="toast-editor"', html=False)
        self.assertContains(response, "toastui-editor-all.min.js")
        self.assertContains(response, reverse("post_editor_image_upload"))

    def test_staff_can_preview_markdown(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("post_editor_preview"),
            data='{"content":"# Preview\\n\\n**Bold** text"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h1>Preview</h1>", response.json()["html"])
        self.assertIn("<strong>Bold</strong>", response.json()["html"])

    def test_staff_can_edit_existing_post(self):
        self.client.force_login(self.staff_user)
        post = Post.objects.create(
            title="Existing",
            slug="existing",
            content="Old content",
            published=False,
        )

        response = self.client.post(
            reverse("post_editor_edit", kwargs={"slug": post.slug}),
            {
                "title": "Existing",
                "slug": "existing",
                "content": "Updated **content**",
                "published": "on",
            },
        )

        post.refresh_from_db()
        self.assertRedirects(response, f"{post.get_editor_url()}?saved=1")
        self.assertEqual(post.content, "Updated **content**")
        self.assertTrue(post.published)

    def test_image_upload_requires_login(self):
        response = self.client.post(reverse("post_editor_image_upload"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_upload_image_for_markdown_embedding(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("post_editor_image_upload"),
            {"image": self.make_image_upload("Header Image.png")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["url"].startswith("/media/blog-images/Header_Image-"))
        self.assertTrue(payload["url"].endswith(".png"))
        self.assertEqual(payload["alt"], "Header Image")

    def test_staff_can_upload_avif_image_for_markdown_embedding(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("post_editor_image_upload"),
            {
                "image": self.make_image_upload(
                    "wide-shot.avif",
                    image_format="AVIF",
                    content_type="image/avif",
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["url"].startswith("/media/blog-images/wide-shot-"))
        self.assertTrue(payload["url"].endswith(".avif"))
        self.assertEqual(payload["alt"], "wide shot")

    def test_image_upload_rejects_non_images(self):
        self.client.force_login(self.staff_user)
        upload = SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")

        response = self.client.post(reverse("post_editor_image_upload"), {"image": upload})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "The uploaded file is not a supported image.")


class PostPublishingTests(TestCase):
    def test_published_at_is_set_on_first_publish_only(self):
        post = Post.objects.create(
            title="Draft",
            slug="draft",
            content="Draft body",
            published=False,
        )

        self.assertIsNone(post.published_at)

        post.published = True
        post.save()
        first_published_at = post.published_at

        self.assertIsNotNone(first_published_at)

        post.title = "Retitled"
        post.save()
        post.refresh_from_db()

        self.assertEqual(post.published_at, first_published_at)

    def test_archive_uses_published_month_not_created_month(self):
        published_at = timezone.datetime(2026, 4, 5, 12, tzinfo=timezone.get_current_timezone())
        post = Post.objects.create(
            title="Published Later",
            slug="published-later",
            content="Body",
            published=True,
            published_at=published_at,
        )
        Post.objects.filter(pk=post.pk).update(created_at=timezone.datetime(2026, 1, 5, 12, tzinfo=timezone.get_current_timezone()))

        april_response = self.client.get(reverse("post_archive_month", kwargs={"year": 2026, "month": 4}))
        january_response = self.client.get(reverse("post_archive_month", kwargs={"year": 2026, "month": 1}))

        self.assertContains(april_response, "Published Later")
        self.assertNotContains(january_response, "Published Later")
