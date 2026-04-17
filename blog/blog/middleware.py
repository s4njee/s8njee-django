from .navigation import LAST_PAGE_COOKIE, LAST_PAGE_COOKIE_MAX_AGE, sign_last_page


class LastPageMiddleware:
    excluded_prefixes = (
        "/admin/",
        "/accounts/",
        "/login",
        "/__debug__/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self._should_store(request, response):
            # Signed cookie instead of session: no DB write per GET. Secure flag
            # follows the request's scheme so local HTTP dev still sets the cookie.
            response.set_cookie(
                LAST_PAGE_COOKIE,
                sign_last_page(request.get_full_path()),
                max_age=LAST_PAGE_COOKIE_MAX_AGE,
                secure=request.is_secure(),
                httponly=True,
                samesite="Lax",
            )
        return response

    def _should_store(self, request, response):
        if request.method != "GET" or request.headers.get("HX-Request") == "true":
            return False
        if response.status_code != 200:
            return False
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return False
        return not request.path_info.startswith(self.excluded_prefixes)
