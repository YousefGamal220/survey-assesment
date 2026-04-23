from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.audit.models import AuditLog
from apps.organizations.tests.factories import OrganizationFactory
from apps.surveys.tests.factories import SurveyFactory


def _client(user, org, role=Membership.Role.ADMIN):
    MembershipFactory(user=user, organization=org, role=role)
    token = AccessToken.for_user(user)
    token["org_id"] = str(org.id)
    token["role"] = role
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


@pytest.mark.django_db
class TestAuditMiddleware:
    def test_authenticated_request_writes_row(self):
        org = OrganizationFactory()
        user = UserFactory()
        c = _client(user, org)

        c.get("/api/v1/surveys/")

        row = AuditLog.objects.latest("created_at")
        assert row.user == user
        assert row.user_email == user.email
        assert row.role == Membership.Role.ADMIN
        assert row.method == "GET"
        assert row.path == "/api/v1/surveys/"
        assert row.status_code == 200
        assert row.organization_id == org.id

    def test_unauthenticated_non_auth_path_not_logged(self):
        """/api/v1/surveys/ without a token — 401 but no row."""
        before = AuditLog.objects.count()
        APIClient().get("/api/v1/surveys/")
        after = AuditLog.objects.count()
        assert before == after

    def test_failed_login_is_logged(self):
        """/api/v1/auth/login is the exception — even unauthenticated
        attempts must be captured (for brute-force forensics)."""
        before = AuditLog.objects.count()
        APIClient().post("/api/v1/auth/login", {"email": "no@x.com", "password": "nope"})
        after = AuditLog.objects.count()
        assert after == before + 1
        row = AuditLog.objects.latest("created_at")
        assert row.method == "POST"
        assert row.path == "/api/v1/auth/login"
        assert row.status_code in (400, 401)

    def test_schema_and_docs_paths_skipped(self):
        before = AuditLog.objects.count()
        APIClient().get("/api/schema/")
        APIClient().get("/api/docs/")
        assert AuditLog.objects.count() == before


@pytest.mark.django_db
class TestAuditViewSet:
    def test_analyst_can_list_own_org(self):
        org = OrganizationFactory()
        user = UserFactory()
        AuditLog.objects.create(
            organization=org,
            user=user,
            user_email=user.email,
            method="GET",
            path="/api/v1/surveys/",
            status_code=200,
        )
        c = _client(user, org, role=Membership.Role.ANALYST)
        res = c.get("/api/v1/audit-log/")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] >= 1

    def test_viewer_forbidden(self):
        org = OrganizationFactory()
        user = UserFactory()
        c = _client(user, org, role=Membership.Role.VIEWER)
        res = c.get("/api/v1/audit-log/")
        assert res.status_code == 403

    def test_cross_tenant_rows_hidden(self):
        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        # Seed a B-row and an A-row
        AuditLog.objects.create(
            organization=org_b,
            method="GET",
            path="/api/v1/b/",
            status_code=200,
        )
        AuditLog.objects.create(
            organization=org_a,
            method="GET",
            path="/api/v1/a/",
            status_code=200,
        )
        user_a = UserFactory()
        c = _client(user_a, org_a, role=Membership.Role.ANALYST)
        res = c.get("/api/v1/audit-log/")
        paths = [r["path"] for r in res.json()["results"]]
        # Our own request lands here too — "/api/v1/audit-log/" — but org_b's
        # path must not show up.
        assert "/api/v1/b/" not in paths
        assert any(p == "/api/v1/a/" for p in paths)

    def test_method_filter(self):
        org = OrganizationFactory()
        user = UserFactory()
        AuditLog.objects.create(
            organization=org,
            user=user,
            method="POST",
            path="/api/v1/x/",
            status_code=201,
        )
        AuditLog.objects.create(
            organization=org,
            user=user,
            method="GET",
            path="/api/v1/x/",
            status_code=200,
        )
        c = _client(user, org, role=Membership.Role.ANALYST)
        res = c.get("/api/v1/audit-log/?method=POST")
        assert res.status_code == 200
        methods = {r["method"] for r in res.json()["results"]}
        # Our own list call is a GET — filter should exclude it
        assert methods == {"POST"}


@pytest.mark.django_db
class TestAppendOnly:
    def test_survey_create_is_logged(self):
        org = OrganizationFactory()
        user = UserFactory()
        c = _client(user, org, role=Membership.Role.ADMIN)

        before = AuditLog.objects.count()
        c.post(
            "/api/v1/surveys/",
            {
                "title": "Demo",
                "sections": [
                    {
                        "position": 0,
                        "title": "S",
                        "fields": [{"key": "q", "position": 0, "type": "short_text", "label": "Q"}],
                    }
                ],
            },
            format="json",
        )
        assert AuditLog.objects.count() == before + 1

    def test_survey_publish_logged_separately(self):
        org = OrganizationFactory()
        user = UserFactory()
        c = _client(user, org, role=Membership.Role.ADMIN)

        survey = SurveyFactory(organization=org)
        before = AuditLog.objects.count()
        c.post(f"/api/v1/surveys/{survey.id}/publish/")
        after = AuditLog.objects.count()
        assert after == before + 1
        row = AuditLog.objects.latest("created_at")
        assert row.path.endswith("/publish/")
        assert row.method == "POST"
