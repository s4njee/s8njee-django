from django.contrib.syndication.views import Feed
from django.urls import reverse
from .models import Post

class LatestPostsFeed(Feed):
    title = "Sanjee's Journal"
    link = "/"
    description = "Latest blog posts from Sanjee's journal."

    def items(self):
        return Post.objects.filter(published=True).order_by('-created_at')[:10]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        # We can use the rendered markdown but for RSS it's better to keep it clean or use a snippet
        return item.content[:300] + '...' if len(item.content) > 300 else item.content

    def item_pubdate(self, item):
        return item.created_at
