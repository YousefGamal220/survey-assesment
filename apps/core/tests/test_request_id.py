from __future__ import annotations

import re

from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.middleware import RequestIdMiddleware

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class TestRequestIdMiddleware:
    def test_generates_id_when_header_missing(self):
        def view(request):
            assert UUID_RE.match(request.id)
            return HttpResponse(status=200)

        mw = RequestIdMiddleware(view)
        response = mw(RequestFactory().get("/"))
        assert UUID_RE.match(response["X-Request-ID"])

    def test_honors_incoming_header(self):
        incoming = "abc123"

        def view(request):
            assert request.id == incoming
            return HttpResponse(status=200)

        mw = RequestIdMiddleware(view)
        response = mw(RequestFactory().get("/", HTTP_X_REQUEST_ID=incoming))
        assert response["X-Request-ID"] == incoming
