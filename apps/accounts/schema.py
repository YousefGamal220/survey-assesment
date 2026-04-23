"""drf-spectacular hook — teach the OpenAPI generator that TenantAuthentication
is a Bearer-JWT scheme so the Swagger UI renders an Authorize button."""

from __future__ import annotations

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class TenantAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.TenantAuthentication"
    name = "BearerAuth"
    match_subclasses = True
    priority = 1

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Org-scoped JWT access token from POST /api/v1/auth/token. "
                "Paste the raw token (no `Bearer ` prefix) — Swagger adds it."
            ),
        }
