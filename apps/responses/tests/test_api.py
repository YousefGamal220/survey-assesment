from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.responses.models import Answer, Response
from apps.responses.tests.factories import ResponseFactory
from apps.surveys.models import Survey
from apps.surveys.tests.factories import FieldFactory, SectionFactory, SurveyFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client(user, org, role=Membership.Role.VIEWER):
    MembershipFactory(user=user, organization=org, role=role)
    token = AccessToken.for_user(user)
    token["org_id"] = str(org.id)
    token["role"] = role
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return c


def _survey(org):
    survey = SurveyFactory(organization=org, status=Survey.Status.PUBLISHED)
    s = SectionFactory(survey=survey, position=0)
    FieldFactory(
        section=s,
        key="name",
        position=0,
        type="short_text",
        label="Name",
        required=True,
    )
    FieldFactory(
        section=s,
        key="ssn",
        position=1,
        type="short_text",
        label="SSN",
        required=False,
        config={"sensitive": True},
    )
    return survey


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestDraftCreation:
    def test_create_returns_201_and_draft(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org)

        res = c.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        assert res.status_code == 201, res.content
        assert res.json()["status"] == "draft"
        assert Response.all_objects.filter(respondent=user).count() == 1

    def test_create_is_idempotent(self):
        """Second POST returns the existing draft, not a duplicate."""
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org)

        r1 = c.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        r2 = c.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        assert r1.status_code == 201
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        assert Response.all_objects.filter(respondent=user).count() == 1

    def test_unauthenticated_rejected(self):
        org = OrganizationFactory()
        survey = _survey(org)
        res = APIClient().post(f"/api/v1/surveys/{survey.id}/responses/", {})
        assert res.status_code == 401


@pytest.mark.django_db
class TestPatchAndSubmit:
    def test_patch_merges_answers_then_submit(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org)

        create = c.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        rid = create.json()["id"]

        patch = c.patch(
            f"/api/v1/surveys/{survey.id}/responses/{rid}/",
            {"answers": {"name": "Alice", "ssn": "123-45-6789"}},
            format="json",
        )
        assert patch.status_code == 200, patch.content

        submit = c.post(f"/api/v1/surveys/{survey.id}/responses/{rid}/submit/", format="json")
        assert submit.status_code == 200, submit.content
        assert submit.json()["status"] == "submitted"

    def test_submit_blocks_missing_required(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org)

        create = c.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        rid = create.json()["id"]
        res = c.post(f"/api/v1/surveys/{survey.id}/responses/{rid}/submit/", format="json")
        assert res.status_code == 400
        # The error envelope wraps validation messages
        body = res.json()
        assert "name" in str(body)

    def test_second_submit_409(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org)

        create = c.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        rid = create.json()["id"]
        c.patch(
            f"/api/v1/surveys/{survey.id}/responses/{rid}/",
            {"answers": {"name": "Alice"}},
            format="json",
        )
        c.post(f"/api/v1/surveys/{survey.id}/responses/{rid}/submit/")
        # Second submit should fail validation (already submitted)
        res = c.post(f"/api/v1/surveys/{survey.id}/responses/{rid}/submit/")
        assert res.status_code == 400


@pytest.mark.django_db
class TestEncryptionOnWire:
    def test_admin_sees_plaintext_others_see_placeholder(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        owner = _client(user, org)

        create = owner.post(f"/api/v1/surveys/{survey.id}/responses/", {}, format="json")
        rid = create.json()["id"]
        owner.patch(
            f"/api/v1/surveys/{survey.id}/responses/{rid}/",
            {"answers": {"name": "Alice", "ssn": "123-45-6789"}},
            format="json",
        )
        owner.post(f"/api/v1/surveys/{survey.id}/responses/{rid}/submit/")

        # Sanity: ciphertext is on disk, plaintext is not in value_json
        row = Answer.all_objects.get(response_id=rid, field_key="ssn")
        assert row.value_json is None
        assert row.value_encrypted is not None

        # Admin retrieve
        admin_user = UserFactory()
        admin = _client(admin_user, org, role=Membership.Role.ADMIN)
        res = admin.get(f"/api/v1/surveys/{survey.id}/responses/{rid}/")
        assert res.status_code == 200
        answers = {a["field_key"]: a["value"] for a in res.json()["answers"]}
        assert answers["ssn"] == "123-45-6789"

        # Analyst retrieve
        analyst_user = UserFactory()
        analyst = _client(analyst_user, org, role=Membership.Role.ANALYST)
        res = analyst.get(f"/api/v1/surveys/{survey.id}/responses/{rid}/")
        assert res.status_code == 200
        answers = {a["field_key"]: a["value"] for a in res.json()["answers"]}
        assert answers["ssn"] == "[encrypted]"


@pytest.mark.django_db
class TestListVisibility:
    def test_viewer_cannot_list(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org, role=Membership.Role.VIEWER)
        res = c.get(f"/api/v1/surveys/{survey.id}/responses/")
        assert res.status_code == 403

    def test_analyst_sees_only_submitted(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        c = _client(user, org, role=Membership.Role.ANALYST)

        # One draft, one submitted — only submitted should appear
        ResponseFactory(survey=survey, status=Response.Status.DRAFT)
        ResponseFactory(survey=survey, status=Response.Status.SUBMITTED)

        res = c.get(f"/api/v1/surveys/{survey.id}/responses/")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 1
        assert body["results"][0]["status"] == "submitted"


@pytest.mark.django_db
class TestTenantIsolation:
    def test_cannot_access_other_orgs_response(self):
        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        survey_b = _survey(org_b)
        resp_b = ResponseFactory(survey=survey_b, status=Response.Status.SUBMITTED)

        # A-client trying to reach B-rows
        user_a = UserFactory()
        c = _client(user_a, org_a, role=Membership.Role.ADMIN)
        res = c.get(f"/api/v1/surveys/{survey_b.id}/responses/{resp_b.id}/")
        assert res.status_code == 404


@pytest.mark.django_db
class TestMineEndpoint:
    def test_returns_only_callers_responses(self):
        org = OrganizationFactory()
        me = UserFactory()
        other = UserFactory()
        survey = _survey(org)
        ResponseFactory(survey=survey, respondent=me, status=Response.Status.SUBMITTED)
        ResponseFactory(survey=survey, respondent=me, status=Response.Status.DRAFT)
        ResponseFactory(survey=survey, respondent=other)

        c = _client(me, org)
        res = c.get("/api/v1/responses/mine/")
        assert res.status_code == 200
        body = res.json()
        assert body["count"] == 2


@pytest.mark.django_db
class TestOwnerOnlyEdits:
    def test_non_owner_cannot_patch(self):
        org = OrganizationFactory()
        owner = UserFactory()
        survey = _survey(org)
        draft = ResponseFactory(survey=survey, respondent=owner)

        other = UserFactory()
        c = _client(other, org, role=Membership.Role.ADMIN)
        res = c.patch(
            f"/api/v1/surveys/{survey.id}/responses/{draft.id}/",
            {"answers": {"name": "x"}},
            format="json",
        )
        # Non-owner can retrieve submitted but the draft isn't submitted → 403 or 404
        assert res.status_code in (403, 404)

    def test_owner_can_delete_draft(self):
        org = OrganizationFactory()
        user = UserFactory()
        survey = _survey(org)
        draft = ResponseFactory(survey=survey, respondent=user)
        c = _client(user, org)
        res = c.delete(f"/api/v1/surveys/{survey.id}/responses/{draft.id}/")
        assert res.status_code == 204
        assert not Response.all_objects.filter(id=draft.id).exists()
