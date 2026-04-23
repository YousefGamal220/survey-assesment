from __future__ import annotations

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIRequestFactory

from apps.core.exceptions import drf_exception_handler


class TestDrfExceptionHandler:
    def _ctx(self):
        return {"request": APIRequestFactory().get("/"), "view": None}

    def test_wraps_validation_error(self):
        exc = ValidationError({"email": ["required"]})
        resp = drf_exception_handler(exc, self._ctx())
        assert resp is not None
        assert resp.status_code == 400
        body = resp.data
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"] == {"email": ["required"]}
        assert "request_id" in body

    def test_wraps_not_found(self):
        resp = drf_exception_handler(NotFound("missing"), self._ctx())
        assert resp is not None
        assert resp.status_code == 404
        assert resp.data["error"]["code"] == "not_found"

    def test_returns_none_for_unhandled(self):
        assert drf_exception_handler(ValueError("x"), self._ctx()) is None
