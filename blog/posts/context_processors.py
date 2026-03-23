from django.db.models.functions import TruncMonth
from django.db.models import Count
from .models import Post


def archive_months(request):
    months = (
        Post.objects.filter(published=True)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('-month')
    )
    return {'archive_months': months}
