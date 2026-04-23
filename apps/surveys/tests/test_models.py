from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.surveys.models import Field, Section, Survey
from apps.surveys.tests.factories import FieldFactory, SectionFactory, SurveyFactory


@pytest.mark.django_db
class TestSurveyVersioning:
    def test_two_surveys_in_same_group_and_org_must_have_distinct_versions(self):
        first = SurveyFactory(version=1)
        with pytest.raises(IntegrityError):
            SurveyFactory(
                organization=first.organization,
                survey_group_id=first.survey_group_id,
                version=1,
            )

    def test_same_version_across_different_groups_is_fine(self):
        a = SurveyFactory(version=1)
        b = SurveyFactory(organization=a.organization, version=1)  # different group_id
        assert a.survey_group_id != b.survey_group_id

    def test_same_group_version_across_different_orgs_is_fine(self):
        a = SurveyFactory(version=1)
        b = SurveyFactory(survey_group_id=a.survey_group_id, version=1)  # different org
        assert a.organization_id != b.organization_id

    def test_default_status_is_draft(self):
        survey = SurveyFactory()
        assert survey.status == Survey.Status.DRAFT


@pytest.mark.django_db
class TestCascade:
    def test_deleting_survey_cascades_to_sections_and_fields(self):
        survey = SurveyFactory()
        section = SectionFactory(survey=survey)
        FieldFactory(section=section)
        survey_id = survey.id
        section_id = section.id
        survey.delete()
        assert Section.all_objects.filter(survey_id=survey_id).count() == 0
        assert Field.all_objects.filter(section_id=section_id).count() == 0


@pytest.mark.django_db
class TestSectionUniqueness:
    def test_two_sections_in_same_survey_cannot_share_position(self):
        survey = SurveyFactory()
        SectionFactory(survey=survey, position=0)
        with pytest.raises(IntegrityError):
            SectionFactory(survey=survey, position=0)


@pytest.mark.django_db
class TestFieldUniqueness:
    def test_two_fields_in_same_section_cannot_share_position(self):
        section = SectionFactory()
        FieldFactory(section=section, position=0)
        with pytest.raises(IntegrityError):
            FieldFactory(section=section, position=0)
