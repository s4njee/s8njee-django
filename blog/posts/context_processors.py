import logging

from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Count
from django.db.models.functions import TruncMonth

from .models import Post


logger = logging.getLogger(__name__)

# Context processors run on every template render, so the archive nav was
# re-executing this TruncMonth aggregate on every page load. Cache it and let
# post saves/deletes invalidate via the signal below.
ARCHIVE_MONTHS_CACHE_KEY = "archive_months"
ARCHIVE_MONTHS_TTL = 60 * 60  # 1 hour; invalidated on Post change via signal.


def archive_months(request):
    months = cache.get(ARCHIVE_MONTHS_CACHE_KEY)
    if months is not None:
        return {"archive_months": months}

    try:
        months = list(
            Post.objects.filter(published=True, published_at__isnull=False)
            .annotate(month=TruncMonth("published_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("-month")
        )
    except DatabaseError:
        # Narrowed from bare Exception: we only want to tolerate DB unavailability
        # (e.g., rendering the 500 page when the primary is down). Other errors
        # are programming bugs and should surface in logs.
        logger.warning("archive_months query failed", exc_info=True)
        return {"archive_months": []}

    cache.set(ARCHIVE_MONTHS_CACHE_KEY, months, ARCHIVE_MONTHS_TTL)
    return {"archive_months": months}
