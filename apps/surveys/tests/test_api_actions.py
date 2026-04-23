from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.surveys.models import Field, Section, Survey
from apps.surveys.tests.factories import FieldFactory, SectionFactory, SurveyFactory


def _admin_client(org):
    user = UserFactory()
    MembershipFactory(user=user, organization=org, role=Membership.Role.ADMIN)
    access = AccessToken.for_user(user)
    access["org_id"] = str(org.id)
    access["role"] = Membership.Role.ADMIN
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, user


@pytest.mark.django_db
class TestPublish:
    def test_draft_publishes_sets_timestamp(self):
        org = OrganizationFactory()
        client, _ = _admin_client(org)
        s = SurveyFactory(organization=org)
        res = client.post(f"/api/v1/surveys/{s.id}/publish/")
        assert res.status_code == 200
        s.refresh_from_db()
        assert s.status == Survey.Status.PUBLISHED
        assert s.published_at is not None

    def test_cannot_publish_twice(self):
        org = OrganizationFactory()
        client, _ = _admin_client(org)
        s = SurveyFactory(organization=org, status=Survey.Status.PUBLISHED)
        res = client.post(f"/api/v1/surveys/{s.id}/publish/")
        assert res.status_code == 409


@pytest.mark.django_db
class TestNewVersion:
    def test_clones_tree_and_bumps_version(self):
        org = OrganizationFactory()
        client, _ = _admin_client(org)
        s = SurveyFactory(organization=org, status=Survey.Status.PUBLISHED, version=1)
        section = SectionFactory(survey=s, position=0, title="Intro")
        FieldFactory(section=section, key="q1", position=0, type="short_text", label="Q1")

        res = client.post(f"/api/v1/surveys/{s.id}/new_version/")
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["version"] == 2
        assert body["status"] == "draft"

        new_survey = Survey.all_objects.get(id=body["id"])
        assert new_survey.survey_group_id == s.survey_group_id
        assert Section.all_objects.filter(survey=new_survey).count() == 1
        assert Field.all_objects.filter(section__survey=new_survey).count() == 1

    def test_cannot_fork_draft(self):
        org = OrganizationFactory()
        client, _ = _admin_client(org)
        s = SurveyFactory(organization=org)  # draft
        res = client.post(f"/api/v1/surveys/{s.id}/new_version/")
        assert res.status_code == 409
