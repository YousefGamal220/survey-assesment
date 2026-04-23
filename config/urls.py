"""URL configuration — version-namespaced API + OpenAPI docs + admin."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

v1_patterns = [
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("", include("apps.surveys.urls", namespace="surveys")),
    path("", include("apps.responses.urls", namespace="responses")),
    path("", include("apps.audit.urls", namespace="audit")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((v1_patterns, "v1"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
