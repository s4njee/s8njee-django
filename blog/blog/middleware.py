from .navigation import LAST_PAGE_SESSION_KEY


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
            request.session[LAST_PAGE_SESSION_KEY] = request.get_full_path()
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
