from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.context import reset_current_organization


class CurrentOrgMiddleware:
    """Resets the contextvar-backed tenant context on response exit.

    The contextvar is *set* by `TenantAuthentication.authenticate()` — which
    runs inside the DRF view dispatch, AFTER Django middleware entry — so
    setting it here would be too early. This middleware only handles the
    reset (via the token stashed by the authenticator) to prevent leakage
    across request/worker reuse.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.get_response(request)
        finally:
            token = getattr(request, "_tenant_token", None)
            if token is not None:
                reset_current_organization(token)
