from __future__ import annotations

import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.authentication import TenantAuthentication
from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.organizations.tests.factories import OrganizationFactory


def _scoped_token(user, org, role: str) -> str:
    token = AccessToken.for_user(user)
    token["org_id"] = str(org.id)
    token["role"] = role
    return str(token)


@pytest.mark.django_db
class TestTenantAuthentication:
    def _req(self, token: str) -> Request:
        raw = APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {token}")
        return Request(raw)

    def test_sets_request_organization_and_membership(self):
        user = UserFactory()
        org = OrganizationFactory()
        m = MembershipFactory(user=user, organization=org, role=Membership.Role.ADMIN)
        request = self._req(_scoped_token(user, org, "admin"))

        auth_user, _validated_token = TenantAuthentication().authenticate(request)
        assert auth_user == user
        assert request.organization == org
        assert request.membership == m

    def test_rejects_when_membership_revoked(self):
        user = UserFactory()
        org = OrganizationFactory()
        MembershipFactory(user=user, organization=org, role=Membership.Role.ADMIN, is_active=False)
        request = self._req(_scoped_token(user, org, "admin"))

        with pytest.raises(AuthenticationFailed):
            TenantAuthentication().authenticate(request)

    def test_rejects_when_organization_inactive(self):
        user = UserFactory()
        org = OrganizationFactory(is_active=False)
        MembershipFactory(user=user, organization=org, role=Membership.Role.ADMIN)
        request = self._req(_scoped_token(user, org, "admin"))

        with pytest.raises(AuthenticationFailed):
            TenantAuthentication().authenticate(request)

    def test_rejects_when_org_id_claim_missing(self):
        user = UserFactory()
        token = AccessToken.for_user(user)
        request = self._req(str(token))

        with pytest.raises(AuthenticationFailed):
            TenantAuthentication().authenticate(request)
