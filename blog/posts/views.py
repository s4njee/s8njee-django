from django.views.generic import ListView, DetailView
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
