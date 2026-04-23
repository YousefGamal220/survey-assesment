"""AuditMiddleware — writes one row per authenticated API request.

Runs AFTER the view so we have `request.user`, `request.organization` (set by
TenantAuthentication), and the final response status. Skips unauthenticated
requests and non-/api/ paths to keep noise down; /api/v1/auth/login is still
captured (status_code tells you success vs. fail).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.audit.models import AuditLog

_AUDITED_PATH_PREFIX = "/api/"
_SKIP_PATHS = {"/api/schema/", "/api/docs/", "/api/redoc/"}


class AuditMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        # Audit must not break the request path — a failed write is a noop.
        # In production this would feed the structured logger in apps.core.logging.
        with contextlib.suppress(Exception):
            self._maybe_record(request, response)
        return response

    @staticmethod
    def _maybe_record(request: HttpRequest, response: HttpResponse) -> None:
        path = request.path
        if not path.startswith(_AUDITED_PATH_PREFIX):
            return
        if any(path.startswith(skip) for skip in _SKIP_PATHS):
            return

        user = getattr(request, "user", None)
        authed = user is not None and getattr(user, "is_authenticated", False)
        # Still capture failed /auth/login attempts — we want brute-force forensics
        # even when there's no authenticated user.
        if not authed and not path.startswith("/api/v1/auth/"):
            return

        membership = getattr(request, "membership", None)
        organization = getattr(request, "organization", None)

        AuditLog.objects.create(
            organization=organization,
            user=user if authed else None,
            user_email=getattr(user, "email", "") if user else "",
            role=getattr(membership, "role", "") or "",
            method=request.method or "",
            path=path[:512],
            status_code=response.status_code,
            request_id=getattr(request, "id", "") or "",
        )
