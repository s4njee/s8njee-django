from django.db.models.functions import TruncMonth
from django.db.models import Count
from .models import Post


def archive_months(request):
    # Context processors inject data into every template render configured in settings.
    try:
        months = (
            Post.objects.filter(published=True, published_at__isnull=False)
            .annotate(month=TruncMonth('published_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('-month')
        )
        return {'archive_months': months}
    except Exception:
        return {'archive_months': []}
