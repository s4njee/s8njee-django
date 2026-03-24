from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
