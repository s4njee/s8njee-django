from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Post
from albums.models import Album

class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Post.objects.filter(published=True)

    def lastmod(self, obj):
        return obj.updated_at

class AlbumSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return Album.objects.all()

    def lastmod(self, obj):
        return obj.updated_at

class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = 'daily'

    def items(self):
        return ['post_list', 'album_list']

    def location(self, item):
        return reverse(item)
