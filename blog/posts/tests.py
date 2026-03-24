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
