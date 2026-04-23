import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.organizations.tests.factories import OrganizationFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestLoginEndpoint:
    def test_login_success_returns_refresh_and_memberships(self, api_client):
        user = UserFactory(email="alice@example.com")
        user.set_password("pw12345!")
        user.save()
        org_1 = OrganizationFactory(name="Acme")
        org_2 = OrganizationFactory(name="Globex")
        MembershipFactory(user=user, organization=org_1, role=Membership.Role.ADMIN)
        MembershipFactory(user=user, organization=org_2, role=Membership.Role.VIEWER)

        res = api_client.post(
            "/api/v1/auth/login",
            {"email": "alice@example.com", "password": "pw12345!"},
            format="json",
        )
        assert res.status_code == 200, res.content
        body = res.json()
        assert "refresh" in body
        assert len(body["memberships"]) == 2
        roles = {m["role"] for m in body["memberships"]}
        assert roles == {"admin", "viewer"}

    def test_login_wrong_password_401(self, api_client):
        user = UserFactory(email="bob@example.com")
        user.set_password("pw12345!")
        user.save()

        res = api_client.post(
            "/api/v1/auth/login",
            {"email": "bob@example.com", "password": "wrong"},
            format="json",
        )
        assert res.status_code == 401

    def test_login_excludes_inactive_memberships(self, api_client):
        user = UserFactory(email="carol@example.com")
        user.set_password("pw12345!")
        user.save()
        org = OrganizationFactory()
        MembershipFactory(user=user, organization=org, is_active=False)

        res = api_client.post(
            "/api/v1/auth/login",
            {"email": "carol@example.com", "password": "pw12345!"},
            format="json",
        )
        assert res.status_code == 200
        assert res.json()["memberships"] == []


@pytest.mark.django_db
class TestTokenEndpoint:
    def test_issues_org_scoped_access_token(self, api_client):
        user = UserFactory(email="eve@example.com")
        user.set_password("pw12345!")
        user.save()
        org = OrganizationFactory()
        MembershipFactory(user=user, organization=org, role=Membership.Role.ANALYST)

        login = api_client.post(
            "/api/v1/auth/login",
            {"email": "eve@example.com", "password": "pw12345!"},
            format="json",
        )
        refresh = login.json()["refresh"]

        res = api_client.post(
            "/api/v1/auth/token",
            {"refresh": refresh, "organization_id": str(org.id)},
            format="json",
        )
        assert res.status_code == 200, res.content
        assert "access" in res.json()

    def test_rejects_when_no_membership(self, api_client):
        user = UserFactory(email="mallory@example.com")
        user.set_password("pw12345!")
        user.save()
        other_org = OrganizationFactory()

        login = api_client.post(
            "/api/v1/auth/login",
            {"email": "mallory@example.com", "password": "pw12345!"},
            format="json",
        )
        refresh = login.json()["refresh"]

        res = api_client.post(
            "/api/v1/auth/token",
            {"refresh": refresh, "organization_id": str(other_org.id)},
            format="json",
        )
        assert res.status_code == 403


@pytest.mark.django_db
class TestLogoutEndpoint:
    def test_logout_blacklists_refresh(self, api_client):
        user = UserFactory(email="logout@example.com")
        user.set_password("pw12345!")
        user.save()
        org = OrganizationFactory()
        MembershipFactory(user=user, organization=org, role=Membership.Role.VIEWER)

        login = api_client.post(
            "/api/v1/auth/login",
            {"email": "logout@example.com", "password": "pw12345!"},
            format="json",
        )
        refresh = login.json()["refresh"]

        res = api_client.post("/api/v1/auth/logout", {"refresh": refresh}, format="json")
        assert res.status_code == 204

    def test_logout_idempotent_on_bad_token(self, api_client):
        res = api_client.post("/api/v1/auth/logout", {"refresh": "not-a-real-token"}, format="json")
        assert res.status_code == 204
