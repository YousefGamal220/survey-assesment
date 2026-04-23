from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.surveys.models import Field, Section, Survey
from apps.surveys.serializers import SurveySerializer


def _ctx(org, user):
    request = MagicMock()
    request.organization = org
    request.user = user
    return {"request": request}


@pytest.mark.django_db
class TestCreateTree:
    def test_create_persists_full_nested_tree(self):
        org = OrganizationFactory()
        user = UserFactory()
        payload = {
            "title": "Demo",
            "description": "",
            "sections": [
                {
                    "position": 0,
                    "title": "Intro",
                    "description": "",
                    "fields": [
                        {
                            "key": "employed",
                            "position": 0,
                            "type": "single_choice",
                            "label": "Are you employed?",
                            "config": {
                                "choices": [
                                    {"value": "yes", "label": "Yes"},
                                    {"value": "no", "label": "No"},
                                ]
                            },
                        }
                    ],
                }
            ],
        }

        ser = SurveySerializer(data=payload, context=_ctx(org, user))
        ser.is_valid(raise_exception=True)
        survey = ser.save()

        assert Survey.all_objects.count() == 1
        assert Section.all_objects.filter(survey=survey).count() == 1
        assert Field.all_objects.filter(section__survey=survey).count() == 1
        assert survey.organization_id == org.id
        assert survey.version == 1
        assert survey.status == Survey.Status.DRAFT


@pytest.mark.django_db
class TestValidateConfigHook:
    def test_single_choice_without_choices_rejected(self):
        org = OrganizationFactory()
        user = UserFactory()
        payload = {
            "title": "Bad",
            "sections": [
                {
                    "position": 0,
                    "title": "S",
                    "fields": [{"key": "x", "position": 0, "type": "single_choice", "label": "?"}],
                }
            ],
        }
        ser = SurveySerializer(data=payload, context=_ctx(org, user))
        assert not ser.is_valid()
        assert "choices" in str(ser.errors)


@pytest.mark.django_db
class TestDuplicateKey:
    def test_duplicate_key_across_sections_rejected(self):
        org = OrganizationFactory()
        user = UserFactory()
        payload = {
            "title": "Dup",
            "sections": [
                {
                    "position": 0,
                    "title": "A",
                    "fields": [{"key": "x", "position": 0, "type": "short_text", "label": "X"}],
                },
                {
                    "position": 1,
                    "title": "B",
                    "fields": [{"key": "x", "position": 0, "type": "short_text", "label": "X2"}],
                },
            ],
        }
        ser = SurveySerializer(data=payload, context=_ctx(org, user))
        assert not ser.is_valid()


@pytest.mark.django_db
class TestUpdateRewritesTree:
    def test_update_replaces_sections(self):
        org = OrganizationFactory()
        user = UserFactory()
        ser = SurveySerializer(
            data={
                "title": "v1",
                "sections": [
                    {
                        "position": 0,
                        "title": "A",
                        "fields": [{"key": "x", "position": 0, "type": "short_text", "label": "X"}],
                    }
                ],
            },
            context=_ctx(org, user),
        )
        ser.is_valid(raise_exception=True)
        survey = ser.save()

        ser2 = SurveySerializer(
            instance=survey,
            data={
                "title": "v1-edited",
                "sections": [
                    {
                        "position": 0,
                        "title": "B",
                        "fields": [{"key": "y", "position": 0, "type": "short_text", "label": "Y"}],
                    }
                ],
            },
            context=_ctx(org, user),
        )
        ser2.is_valid(raise_exception=True)
        ser2.save()

        survey.refresh_from_db()
        assert survey.title == "v1-edited"
        assert list(Field.all_objects.values_list("key", flat=True)) == ["y"]
