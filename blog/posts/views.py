import json
import uuid
from datetime import date
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.text import get_valid_filename
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView
from PIL import Image, UnidentifiedImageError

from .forms import PostEditorForm
from .markdown import render_markdown
from .models import Post


BLOG_IMAGE_UPLOAD_DIR = "blog-images"
BLOG_IMAGE_MAX_BYTES = 10 * 1024 * 1024
BLOG_IMAGE_FORMAT_EXTENSIONS = {
    "AVIF": ".avif",
    "JPEG": ".jpg",
    "PNG": ".png",
    "GIF": ".gif",
    "WEBP": ".webp",
}


class PostListView(ListView):
    # ListView supplies pagination and exposes the queryset as context_object_name.
    model = Post
    template_name = 'posts/post_list.html'
    context_object_name = 'posts'
    queryset = Post.objects.filter(published=True).order_by("-published_at", "-created_at")
    paginate_by = 10


class PostMonthArchiveView(ListView):
    # Overriding get_queryset lets the same generic view serve filtered archives.
    model = Post
    template_name = 'posts/post_list.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        return Post.objects.filter(
            published=True,
            published_at__year=self.kwargs['year'],
            published_at__month=self.kwargs['month'],
        )

    def get_context_data(self, **kwargs):
        # get_context_data is the standard class-based-view hook for template data.
        context = super().get_context_data(**kwargs)
        context['archive_label'] = date(
            int(self.kwargs['year']), int(self.kwargs['month']), 1
        ).strftime('%B %Y')
        return context


class PostDetailView(DetailView):
    # DetailView fetches one object and returns 404 when the queryset cannot find it.
    model = Post
    template_name = 'posts/post_detail.html'
    context_object_name = 'post'
    queryset = Post.objects.filter(published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        if post.published_at:
            published_qs = Post.objects.filter(published=True, published_at__isnull=False)
            context['previous_post'] = (
                published_qs.filter(published_at__lt=post.published_at)
                .order_by('-published_at')
                .first()
            )
            context['next_post'] = (
                published_qs.filter(published_at__gt=post.published_at)
                .order_by('published_at')
                .first()
            )
        return context


@method_decorator(staff_member_required, name="dispatch")
class PostEditorView(TemplateView):
    # method_decorator applies a function decorator to class-based view dispatch().
    template_name = "posts/post_editor.html"

    def get_post(self):
        slug = self.kwargs.get("slug")
        if not slug:
            return None
        return get_object_or_404(Post, slug=slug)

    def get_form(self, data=None, instance=None):
        return PostEditorForm(data=data, instance=instance)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or self.get_form(instance=self.get_post())
        post = kwargs.get("post", self.get_post())
        preview_source = form.data.get("content") if form.is_bound else getattr(post, "content", "")
        context.update(
            {
                "form": form,
                "post": post,
                "saved": self.request.GET.get("saved") == "1",
                "preview_html": render_markdown(preview_source or ""),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        post = self.get_post()
        # Passing instance makes this ModelForm update instead of create.
        form = self.get_form(data=request.POST, instance=post)
        if form.is_valid():
            saved_post = form.save()
            return redirect(f"{saved_post.get_editor_url()}?saved=1")
        return self.render_to_response(self.get_context_data(form=form, post=post))


@method_decorator(staff_member_required, name="dispatch")
class PostEditorPreviewView(View):
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)
        return JsonResponse({"html": render_markdown(payload.get("content", ""))})


@method_decorator(staff_member_required, name="dispatch")
class PostEditorImageUploadView(View):
    def post(self, request, *args, **kwargs):
        # Uploaded files live in request.FILES, separate from normal POST fields.
        uploaded_image = request.FILES.get("image")
        if not uploaded_image:
            return JsonResponse({"error": "Choose an image to upload."}, status=400)

        if uploaded_image.size > BLOG_IMAGE_MAX_BYTES:
            return JsonResponse({"error": "Images must be 10 MB or smaller."}, status=400)

        try:
            image = Image.open(uploaded_image)
            image.verify()
        except (UnidentifiedImageError, OSError):
            return JsonResponse({"error": "The uploaded file is not a supported image."}, status=400)

        extension = BLOG_IMAGE_FORMAT_EXTENSIONS.get(image.format)
        if not extension:
            return JsonResponse({"error": "Use an AVIF, JPEG, PNG, GIF, or WebP image."}, status=400)

        uploaded_image.seek(0)
        original_name = Path(uploaded_image.name).stem
        safe_name = get_valid_filename(original_name) or "image"
        filename = f"{safe_name}-{uuid.uuid4().hex[:12]}{extension}"
        # default_storage follows STORAGES, so this writes locally or to S3.
        saved_path = default_storage.save(f"{BLOG_IMAGE_UPLOAD_DIR}/{filename}", uploaded_image)

        return JsonResponse(
            {
                "url": default_storage.url(saved_path),
                "alt": original_name.replace("-", " ").replace("_", " ").strip() or "Uploaded image",
            }
        )


def handler404(request, exception=None):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)
