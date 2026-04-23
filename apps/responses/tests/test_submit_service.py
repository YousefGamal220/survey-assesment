from __future__ import annotations

import pytest
from rest_framework.exceptions import ValidationError

from apps.responses.models import Answer, Response
from apps.responses.services import submit_response, upsert_draft_answers
from apps.responses.tests.factories import ResponseFactory
from apps.surveys.models import Section, Survey
from apps.surveys.tests.factories import FieldFactory, SectionFactory, SurveyFactory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _survey_with_fields(**kwargs):
    """Build a published survey with two fields — `employed` (single_choice)
    and `company_name` (short_text, conditionally visible)."""
    survey = SurveyFactory(status=Survey.Status.PUBLISHED, **kwargs)
    section = SectionFactory(survey=survey, position=0)
    FieldFactory(
        section=section,
        key="employed",
        position=0,
        type="single_choice",
        label="Employed?",
        required=True,
        config={
            "choices": [
                {"value": "yes", "label": "Yes"},
                {"value": "no", "label": "No"},
            ]
        },
    )
    FieldFactory(
        section=section,
        key="company_name",
        position=1,
        type="short_text",
        label="Company",
        required=True,
        config={},
        visible_when={"field": "employed", "op": "eq", "value": "yes"},
    )
    return survey


@pytest.fixture
def survey():
    return _survey_with_fields()


@pytest.fixture
def draft(survey):
    return ResponseFactory(survey=survey)


# ---------------------------------------------------------------------------
# upsert_draft_answers
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestUpsertDraftAnswers:
    def test_creates_and_updates(self, draft):
        upsert_draft_answers(draft, {"employed": "yes"})
        upsert_draft_answers(draft, {"employed": "no", "company_name": "ACME"})

        rows = {a.field_key: a for a in Answer.all_objects.filter(response=draft)}
        assert rows["employed"].value_json == "no"
        assert rows["company_name"].value_json == "ACME"

    def test_encrypts_sensitive_fields(self, survey):
        # Flip `company_name` to sensitive
        FieldFactory(
            section=Section.all_objects.filter(survey=survey).first(),
            key="ssn",
            position=2,
            type="short_text",
            label="SSN",
            required=False,
            config={"sensitive": True},
        )
        r = ResponseFactory(survey=survey)
        upsert_draft_answers(r, {"ssn": "123-45-6789"})
        row = Answer.all_objects.get(response=r, field_key="ssn")
        assert row.value_json is None
        assert row.value_encrypted is not None
        assert row.value == "123-45-6789"

    def test_rejects_writes_to_submitted(self, draft):
        draft.status = Response.Status.SUBMITTED
        draft.save()
        with pytest.raises(ValidationError):
            upsert_draft_answers(draft, {"employed": "yes"})


# ---------------------------------------------------------------------------
# submit_response
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestSubmitResponse:
    def test_happy_path(self, draft):
        upsert_draft_answers(draft, {"employed": "no"})
        submit_response(draft)
        draft.refresh_from_db()
        assert draft.status == Response.Status.SUBMITTED
        assert draft.submitted_at is not None

    def test_required_visible_missing_rejected(self, draft):
        # "employed" is required — no answers at all
        with pytest.raises(ValidationError) as exc:
            submit_response(draft)
        assert "employed" in exc.value.detail

    def test_required_hidden_is_ok(self, draft):
        # `employed = no` → `company_name` hidden → not required
        upsert_draft_answers(draft, {"employed": "no"})
        submit_response(draft)

    def test_required_visible_empty_rejected(self, draft):
        # `employed = yes` → `company_name` becomes required, but we leave it blank
        upsert_draft_answers(draft, {"employed": "yes", "company_name": ""})
        with pytest.raises(ValidationError) as exc:
            submit_response(draft)
        assert "company_name" in exc.value.detail

    def test_wrong_type_rejected(self, draft):
        # "employed" expects single_choice value from its choices
        upsert_draft_answers(draft, {"employed": "maybe"})
        with pytest.raises(ValidationError) as exc:
            submit_response(draft)
        assert "employed" in exc.value.detail

    def test_unknown_key_rejected(self, draft):
        upsert_draft_answers(draft, {"employed": "no", "bogus_key": "x"})
        with pytest.raises(ValidationError) as exc:
            submit_response(draft)
        assert "bogus_key" in exc.value.detail

    def test_already_submitted_rejected(self, draft):
        upsert_draft_answers(draft, {"employed": "no"})
        submit_response(draft)
        with pytest.raises(ValidationError):
            submit_response(draft)

    def test_cross_section_dependency(self):
        """A field in section 2 referencing a field from section 1 — key
        requirement of the take-home."""
        survey = SurveyFactory(status=Survey.Status.PUBLISHED)
        s1 = SectionFactory(survey=survey, position=0)
        s2 = SectionFactory(survey=survey, position=1)
        FieldFactory(
            section=s1,
            key="country",
            position=0,
            type="short_text",
            label="Country",
            required=True,
        )
        FieldFactory(
            section=s2,
            key="state",
            position=0,
            type="short_text",
            label="State",
            required=True,
            visible_when={"field": "country", "op": "eq", "value": "US"},
        )
        r = ResponseFactory(survey=survey)

        # Non-US answer hides "state" — no state required
        upsert_draft_answers(r, {"country": "UK"})
        submit_response(r)

    def test_required_visible_list_empty_rejected(self):
        """Empty multi_choice list should be treated as unanswered."""
        survey = SurveyFactory(status=Survey.Status.PUBLISHED)
        s = SectionFactory(survey=survey, position=0)
        FieldFactory(
            section=s,
            key="interests",
            position=0,
            type="multi_choice",
            label="Interests",
            required=True,
            config={"choices": [{"value": "a", "label": "A"}]},
        )
        r = ResponseFactory(survey=survey)
        upsert_draft_answers(r, {"interests": []})
        with pytest.raises(ValidationError) as exc:
            submit_response(r)
        assert "interests" in exc.value.detail
