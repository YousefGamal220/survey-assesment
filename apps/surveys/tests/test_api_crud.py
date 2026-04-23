from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.surveys.models import Survey
from apps.surveys.tests.factories import SurveyFactory


def _auth_client(user, org, role=Membership.Role.ADMIN):
    MembershipFactory(user=user, organization=org, role=role)
    access = AccessToken.for_user(user)
    access["org_id"] = str(org.id)
    access["role"] = role
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


MIN_PAYLOAD = {
    "title": "Demo",
    "description": "",
    "sections": [
        {
            "position": 0,
            "title": "S1",
            "fields": [{"key": "q1", "position": 0, "type": "short_text", "label": "Q1"}],
        }
    ],
}


@pytest.mark.django_db
class TestAuthGates:
    def test_unauthenticated_401(self):
        res = APIClient().get("/api/v1/surveys/")
        assert res.status_code == 401

    def test_viewer_cannot_create(self):
        user = UserFactory()
        org = OrganizationFactory()
        client = _auth_client(user, org, role=Membership.Role.VIEWER)
        res = client.post("/api/v1/surveys/", MIN_PAYLOAD, format="json")
        assert res.status_code == 403

    def test_analyst_can_read_but_not_write(self):
        user = UserFactory()
        org = OrganizationFactory()
        client = _auth_client(user, org, role=Membership.Role.ANALYST)
        SurveyFactory(organization=org)
        assert client.get("/api/v1/surveys/").status_code == 200
        assert client.post("/api/v1/surveys/", MIN_PAYLOAD, format="json").status_code == 403

    def test_admin_can_create(self):
        user = UserFactory()
        org = OrganizationFactory()
        client = _auth_client(user, org, role=Membership.Role.ADMIN)
        res = client.post("/api/v1/surveys/", MIN_PAYLOAD, format="json")
        assert res.status_code == 201, res.content
        assert Survey.all_objects.filter(organization=org).count() == 1


@pytest.mark.django_db
class TestTenantIsolation:
    def test_org_a_cannot_see_org_b_surveys(self):
        user_a = UserFactory()
        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        SurveyFactory(organization=org_b, title="B-only")
        client = _auth_client(user_a, org_a)
        res = client.get("/api/v1/surveys/")
        assert res.status_code == 200
        assert res.json()["count"] == 0

    def test_org_a_cannot_retrieve_org_b_survey_by_id(self):
        user_a = UserFactory()
        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        s = SurveyFactory(organization=org_b)
        client = _auth_client(user_a, org_a)
        res = client.get(f"/api/v1/surveys/{s.id}/")
        assert res.status_code == 404


@pytest.mark.django_db
class TestDraftOnlyEditing:
    def test_published_cannot_be_patched(self):
        user = UserFactory()
        org = OrganizationFactory()
        client = _auth_client(user, org)
        s = SurveyFactory(organization=org, status=Survey.Status.PUBLISHED)
        res = client.patch(f"/api/v1/surveys/{s.id}/", {"title": "nope"}, format="json")
        assert res.status_code == 400
        assert "draft" in str(res.json()).lower()


@pytest.mark.django_db
class TestSoftArchiveOnDelete:
    def test_delete_sets_status_archived(self):
        user = UserFactory()
        org = OrganizationFactory()
        client = _auth_client(user, org)
        s = SurveyFactory(organization=org, status=Survey.Status.PUBLISHED)
        res = client.delete(f"/api/v1/surveys/{s.id}/")
        assert res.status_code == 204
        s.refresh_from_db()
        assert s.status == Survey.Status.ARCHIVED
