import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView

from .forms import PostEditorForm
from .markdown import render_markdown
from .models import Post


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
