from __future__ import annotations

import pytest
from django.core.cache import cache

from apps.responses.services import cache_survey_payload, get_cached_survey_payload
from apps.responses.signals import SURVEY_CACHE_KEY
from apps.surveys.tests.factories import FieldFactory, SectionFactory, SurveyFactory


@pytest.mark.django_db
class TestSurveyCache:
    def setup_method(self):
        cache.clear()

    def test_miss_returns_none(self):
        survey = SurveyFactory()
        assert get_cached_survey_payload(survey.id) is None

    def test_set_then_get(self):
        survey = SurveyFactory()
        cache_survey_payload(survey.id, {"title": "cached"})
        assert get_cached_survey_payload(survey.id) == {"title": "cached"}

    def test_survey_save_invalidates(self):
        survey = SurveyFactory()
        cache_survey_payload(survey.id, {"title": "stale"})
        # Touching the survey must evict the cache entry
        survey.title = "fresh"
        survey.save()
        assert get_cached_survey_payload(survey.id) is None

    def test_section_save_invalidates_parent_survey(self):
        survey = SurveyFactory()
        section = SectionFactory(survey=survey)
        cache_survey_payload(survey.id, {"stale": True})
        section.title = "new title"
        section.save()
        assert cache.get(SURVEY_CACHE_KEY.format(id=survey.id)) is None

    def test_field_save_invalidates_parent_survey(self):
        survey = SurveyFactory()
        section = SectionFactory(survey=survey)
        field = FieldFactory(section=section)
        cache_survey_payload(survey.id, {"stale": True})
        field.label = "new label"
        field.save()
        assert cache.get(SURVEY_CACHE_KEY.format(id=survey.id)) is None
