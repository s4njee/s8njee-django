import json
import uuid
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
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
    model = Post
    template_name = 'posts/post_list.html'
    context_object_name = 'posts'
    queryset = Post.objects.filter(published=True)
    paginate_by = 10


class PostMonthArchiveView(ListView):
    model = Post
    template_name = 'posts/post_list.html'
    context_object_name = 'posts'
    paginate_by = 10

    def get_queryset(self):
        return Post.objects.filter(
            published=True,
            created_at__year=self.kwargs['year'],
            created_at__month=self.kwargs['month'],
        )


class PostDetailView(DetailView):
    model = Post
    template_name = 'posts/post_detail.html'
    context_object_name = 'post'
    queryset = Post.objects.filter(published=True)


@method_decorator(staff_member_required, name="dispatch")
class PostEditorView(TemplateView):
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
        saved_path = default_storage.save(f"{BLOG_IMAGE_UPLOAD_DIR}/{filename}", uploaded_image)

        return JsonResponse(
            {
                "url": default_storage.url(saved_path),
                "alt": original_name.replace("-", " ").replace("_", " ").strip() or "Uploaded image",
            }
        )
