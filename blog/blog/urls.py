from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from django.contrib.sitemaps.views import sitemap
from posts.sitemaps import PostSitemap, AlbumSitemap, StaticViewSitemap
from posts.feeds import LatestPostsFeed

sitemaps = {
    'static': StaticViewSitemap,
    'posts': PostSitemap,
    'albums': AlbumSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path('feed/', LatestPostsFeed(), name='post_feed'),
    path('photos/', include('albums.urls')),
    path('blog/', RedirectView.as_view(url='/', permanent=True)),
    path('', include('posts.urls')),
]

if settings.MEDIA_URL.startswith('/'):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
