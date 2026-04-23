"""Core exceptions and the DRF exception handler (error envelope)."""

from __future__ import annotations

from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

from apps.core.middleware import current_request_id


class TenantNotSetError(RuntimeError):
    """Raised when a tenant-scoped query runs without a tenant context set."""


_CODE_MAP: dict[type[exceptions.APIException], str] = {
    exceptions.ValidationError: "validation_error",
    exceptions.AuthenticationFailed: "authentication_failed",
    exceptions.NotAuthenticated: "not_authenticated",
    exceptions.PermissionDenied: "permission_denied",
    exceptions.NotFound: "not_found",
    exceptions.MethodNotAllowed: "method_not_allowed",
    exceptions.Throttled: "throttled",
    exceptions.UnsupportedMediaType: "unsupported_media_type",
    exceptions.ParseError: "parse_error",
}


def _code_for(exc: Exception) -> str:
    for cls, code in _CODE_MAP.items():
        if isinstance(exc, cls):
            return code
    return "server_error"


def drf_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_default_handler(exc, context)
    if response is None:
        return None

    code = _code_for(exc)
    if isinstance(exc, exceptions.ValidationError):
        details = exc.detail
        message = "Validation failed."
    else:
        detail = getattr(exc, "detail", str(exc))
        if isinstance(detail, (dict, list)):
            details = detail
            message = "Error."
        else:
            details = None
            message = str(detail)

    response.data = {
        "error": {"code": code, "message": message, "details": details},
        "request_id": current_request_id(),
    }
    return response


__all__ = ["TenantNotSetError", "drf_exception_handler", "status"]
