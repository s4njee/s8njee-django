from django.conf import settings
from django.core.signing import BadSignature, Signer
from django.utils.http import url_has_allowed_host_and_scheme


# The last public page the visitor saw lives in a signed cookie rather than the
# session store. Sessions wrote to the DB on every GET just to remember one URL;
# a cookie keeps that state on the client and drops the per-request DB write.
LAST_PAGE_COOKIE = "last_public_page"
LAST_PAGE_COOKIE_MAX_AGE = 60 * 60 * 24  # 24 hours is plenty for a login round-trip.

_signer = Signer(salt="last-public-page")


def sign_last_page(path: str) -> str:
    return _signer.sign(path)


def read_last_page(request) -> str | None:
    # Unsign rejects tampered values; pair that with the host check in
    # safe_next_url for defence in depth against open-redirect attempts.
    raw = request.COOKIES.get(LAST_PAGE_COOKIE)
    if not raw:
        return None
    try:
        return _signer.unsign(raw)
    except BadSignature:
        return None


def safe_next_url(request, candidate=None):
    next_url = candidate or read_last_page(request) or settings.LOGIN_REDIRECT_URL
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return settings.LOGIN_REDIRECT_URL
