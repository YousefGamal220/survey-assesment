from __future__ import annotations

import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

_request_id_var: ContextVar[str | None] = ContextVar("survey_request_id", default=None)

HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"


def current_request_id() -> str | None:
    return _request_id_var.get()


class RequestIdMiddleware:
    """Reads `X-Request-ID` or generates a UUID; stores on request + context var
    so loggers can inject it. Echoed back on the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.META.get(HEADER)
        request_id = incoming or str(uuid.uuid4())
        request.id = request_id  # type: ignore[attr-defined]
        token = _request_id_var.set(request_id)
        try:
            response = self.get_response(request)
            response[RESPONSE_HEADER] = request_id
            return response
        finally:
            _request_id_var.reset(token)
