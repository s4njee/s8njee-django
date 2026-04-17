from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from posts.models import Post


class LoginRedirectTests(TestCase):
    def test_manual_login_uses_last_public_page_as_admin_next(self):
        post = Post.objects.create(
            title="Return Target",
            slug="return-target",
            content="A public page.",
            published=True,
        )
        last_page = reverse("post_detail", kwargs={"slug": post.slug})

        self.client.get(last_page)
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/admin/login/?{urlencode({'next': last_page})}")

    def test_login_without_trailing_slash_reaches_login_route(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/login/")

    def test_login_next_query_overrides_last_public_page(self):
        self.client.get(reverse("post_list"))

        response = self.client.get("/login/?next=/photos/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/login/?next=%2Fphotos%2F")

    def test_authenticated_login_redirects_to_last_public_page(self):
        user = get_user_model().objects.create_user(
            username="editor",
            password="testpass123",
            is_staff=True,
        )
        self.client.get(reverse("post_list"))
        self.client.force_login(user)

        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("post_list"))
