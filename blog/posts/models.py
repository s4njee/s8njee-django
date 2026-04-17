from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from .markdown import render_markdown


class Post(models.Model):
    # Django model fields define both the database schema and form/admin metadata.
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    published = models.BooleanField(default=False)

    class Meta:
        # Meta options let the model declare default ORM behavior.
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        # Django uses get_absolute_url in admin, feeds, sitemaps, and templates.
        return reverse('post_detail', kwargs={'slug': self.slug})

    def get_editor_url(self):
        return reverse('post_editor_edit', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        # Model.save() is the final hook before Django writes this row.
        if self.published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @cached_property
    def rendered_content(self):
        # cached_property avoids re-rendering markdown multiple times per request.
        return render_markdown(self.content)


# Keep the import local so test code that imports posts.models first doesn't
# create a circular dependency through context_processors.
@receiver([post_save, post_delete], sender=Post)
def invalidate_archive_months_cache(sender, instance, **kwargs):
    from .context_processors import ARCHIVE_MONTHS_CACHE_KEY
    cache.delete(ARCHIVE_MONTHS_CACHE_KEY)
