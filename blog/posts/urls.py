from django.urls import path
from . import views

urlpatterns = [
    path('', views.PostListView.as_view(), name='post_list'),
    path('archive/<int:year>/<int:month>/', views.PostMonthArchiveView.as_view(), name='post_archive_month'),
    path('<slug:slug>/', views.PostDetailView.as_view(), name='post_detail'),
]
