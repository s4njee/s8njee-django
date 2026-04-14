from django.contrib import admin
from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    # ModelAdmin customizes how this model appears in Django's built-in admin.
    list_display = ('title', 'slug', 'published_at', 'created_at', 'published')
    list_filter = ('published', 'published_at', 'created_at')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}
