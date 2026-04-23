from __future__ import annotations

import pytest

from apps.responses.models import Response
from apps.responses.services import submit_response, upsert_draft_answers
from apps.responses.tasks import (
    aggregate_response_counts,
    export_survey_csv,
    per_field_answer_histogram,
    send_bulk_invitations,
)
from apps.responses.tests.factories import ResponseFactory
from apps.surveys.models import Survey
from apps.surveys.tests.factories import FieldFactory, SectionFactory, SurveyFactory


@pytest.mark.django_db
class TestExportSurveyCsv:
    def test_csv_with_encrypted_column_redacts(self):
        survey = SurveyFactory(status=Survey.Status.PUBLISHED)
        section = SectionFactory(survey=survey, position=0)
        FieldFactory(
            section=section,
            key="name",
            position=0,
            type="short_text",
            label="Name",
            required=True,
        )
        FieldFactory(
            section=section,
            key="ssn",
            position=1,
            type="short_text",
            label="SSN",
            required=False,
            config={"sensitive": True},
        )
        r = ResponseFactory(survey=survey)
        upsert_draft_answers(r, {"name": "Alice", "ssn": "123-45-6789"})
        submit_response(r)

        out = export_survey_csv.delay(str(survey.id)).get()

        lines = out.strip().split("\n")
        assert lines[0].startswith("response_id,submitted_at,respondent_email,name,ssn")
        # Plain field reflected; encrypted field shows redaction token
        assert "Alice" in lines[1]
        assert "[encrypted]" in lines[1]
        assert "123-45-6789" not in out


@pytest.mark.django_db
class TestAggregateCounts:
    def test_counts(self):
        survey = SurveyFactory()
        ResponseFactory(survey=survey, status=Response.Status.DRAFT)
        ResponseFactory(survey=survey, status=Response.Status.SUBMITTED)
        ResponseFactory(survey=survey, status=Response.Status.SUBMITTED)
        counts = aggregate_response_counts.delay(str(survey.id)).get()
        assert counts == {"draft": 1, "submitted": 2}


@pytest.mark.django_db
class TestHistogram:
    def test_counts_plain_values_only(self):
        survey = SurveyFactory(status=Survey.Status.PUBLISHED)
        section = SectionFactory(survey=survey, position=0)
        FieldFactory(
            section=section,
            key="color",
            position=0,
            type="single_choice",
            label="Color",
            required=True,
            config={
                "choices": [
                    {"value": "red", "label": "Red"},
                    {"value": "blue", "label": "Blue"},
                ]
            },
        )
        for value in ("red", "red", "blue"):
            r = ResponseFactory(survey=survey)
            upsert_draft_answers(r, {"color": value})
            submit_response(r)

        hist = per_field_answer_histogram.delay(str(survey.id), "color").get()
        assert hist == {"red": 2, "blue": 1}


class TestBulkInvitations:
    def test_returns_recipient_count(self):
        got = send_bulk_invitations.delay(
            "00000000-0000-0000-0000-000000000000",
            ["a@x.com", "b@x.com", "c@x.com"],
        ).get()
        assert got == 3
