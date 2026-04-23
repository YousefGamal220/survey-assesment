from __future__ import annotations

from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import Membership
from apps.core.context import set_current_organization
from apps.organizations.models import Organization


class TenantAuthentication(JWTAuthentication):
    """JWT auth + org-scoping.

    Successful auth attaches `request.organization` and `request.membership`
    in addition to the user set by the parent class. Revoked memberships and
    inactive orgs reject even if the JWT signature is still valid.
    """

    def authenticate(self, request) -> tuple[Any, Any] | None:
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result

        org_id = validated_token.payload.get("org_id")
        if not org_id:
            raise AuthenticationFailed("token missing org_id claim")

        try:
            org = Organization.objects.get(pk=org_id, is_active=True)
        except Organization.DoesNotExist as exc:
            raise AuthenticationFailed("organization not found or inactive") from exc

        try:
            membership = Membership.objects.get(user_id=user.pk, organization=org, is_active=True)
        except Membership.DoesNotExist as exc:
            raise AuthenticationFailed("membership revoked") from exc

        request.organization = org
        request.membership = membership
        # Propagate onto the underlying Django request too, so middleware
        # running AFTER the view (audit, reset-on-exit) can read them.
        # DRF's Request wrapper does NOT forward setattr by default, so this
        # must be explicit.
        inner = getattr(request, "_request", None)
        if inner is not None:
            inner.organization = org
            inner.membership = membership
        # DRF auth runs inside dispatch, after middleware entry — so set the
        # contextvar here and let CurrentOrgMiddleware reset it on response exit.
        token = set_current_organization(org)
        request._tenant_token = token
        if inner is not None:
            inner._tenant_token = token
        return user, validated_token
