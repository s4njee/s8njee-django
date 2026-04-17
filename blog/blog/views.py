from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET

from .navigation import safe_next_url


@require_GET
def login_redirect(request):
    next_url = safe_next_url(request, request.GET.get("next"))
    if request.user.is_authenticated:
        return redirect(next_url)
    admin_login_url = reverse("admin:login")
    return redirect(f"{admin_login_url}?{urlencode({'next': next_url})}")
