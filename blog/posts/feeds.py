from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.safestring import mark_safe
from .models import Post


class LatestPostsFeed(Feed):
    title = "Sanjee's Journal"
    link = "/"
    description = "Latest blog posts from Sanjee's journal."
    feed_type = Rss201rev2Feed

    def items(self):
        return Post.objects.filter(published=True).order_by('-published_at', '-created_at')[:25]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return mark_safe(item.rendered_content)

    def item_pubdate(self, item):
        return item.published_at or item.created_at
