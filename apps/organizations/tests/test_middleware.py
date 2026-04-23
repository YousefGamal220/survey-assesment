import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.core.context import current_organization, set_current_organization
from apps.organizations.middleware import CurrentOrgMiddleware
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
class TestCurrentOrgMiddleware:
    def test_resets_context_when_auth_stashed_a_token(self):
        """Simulates TenantAuthentication having set the contextvar and stashed
        the reset-token on the request. The middleware must consume it on exit."""
        org = OrganizationFactory()
        captured = {}

        def view(request):
            captured["org_during_view"] = current_organization()
            return HttpResponse(status=200)

        mw = CurrentOrgMiddleware(view)
        request = RequestFactory().get("/")
        # Emulate the authenticator:
        request._tenant_token = set_current_organization(org)

        mw(request)

        assert captured["org_during_view"] == org
        assert current_organization() is None

    def test_no_reset_when_no_token_stashed(self):
        """Requests without a tenant token (e.g. unauthenticated paths) are a no-op."""
        captured = {}

        def view(request):
            captured["org"] = current_organization()
            return HttpResponse(status=200)

        mw = CurrentOrgMiddleware(view)
        request = RequestFactory().get("/")
        mw(request)
        assert captured["org"] is None
