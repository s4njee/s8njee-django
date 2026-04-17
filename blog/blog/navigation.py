from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


LAST_PAGE_SESSION_KEY = "last_public_page"


def safe_next_url(request, candidate=None):
    next_url = candidate or request.session.get(LAST_PAGE_SESSION_KEY) or settings.LOGIN_REDIRECT_URL
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return settings.LOGIN_REDIRECT_URL
