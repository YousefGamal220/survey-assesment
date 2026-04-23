from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.accounts.models import Membership
from apps.responses.models import Answer, Response
from apps.responses.tests.factories import AnswerFactory, ResponseFactory


@pytest.mark.django_db
class TestDraftUniqueness:
    def test_one_draft_per_survey_respondent(self):
        first = ResponseFactory()
        with pytest.raises(IntegrityError):
            ResponseFactory(
                organization=first.organization,
                survey=first.survey,
                respondent=first.respondent,
            )

    def test_submitted_can_coexist_with_draft(self):
        first = ResponseFactory(status=Response.Status.SUBMITTED)
        # A new draft for the same (org, survey, respondent) is fine
        second = ResponseFactory(
            organization=first.organization,
            survey=first.survey,
            respondent=first.respondent,
        )
        assert second.status == Response.Status.DRAFT

    def test_multiple_submitted_responses_allowed(self):
        first = ResponseFactory(status=Response.Status.SUBMITTED)
        second = ResponseFactory(
            organization=first.organization,
            survey=first.survey,
            respondent=first.respondent,
            status=Response.Status.SUBMITTED,
        )
        assert first.id != second.id


@pytest.mark.django_db
class TestAnswerCascade:
    def test_deleting_response_cascades_to_answers(self):
        answer = AnswerFactory()
        rid = answer.response_id
        answer.response.delete()
        assert Answer.all_objects.filter(response_id=rid).count() == 0


@pytest.mark.django_db
class TestAnswerUniqueness:
    def test_same_key_within_response_rejected(self):
        response = ResponseFactory()
        AnswerFactory(response=response, field_key="q1")
        with pytest.raises(IntegrityError):
            AnswerFactory(response=response, field_key="q1")


@pytest.mark.django_db
class TestEncryptionDispatch:
    def test_plain_round_trip(self):
        a = AnswerFactory()
        a.set_value(42, sensitive=False)
        a.save()
        a.refresh_from_db()
        assert a.value_json == 42
        assert a.value_encrypted is None
        assert a.value == 42

    def test_sensitive_is_encrypted_at_rest(self):
        a = AnswerFactory()
        a.set_value("sensitive-secret-123", sensitive=True)
        a.save()
        a.refresh_from_db()

        assert a.value_json is None
        assert a.value_encrypted is not None
        # Column holds opaque ciphertext, never the plaintext
        assert "sensitive-secret-123" not in a.value_encrypted
        assert a.value == "sensitive-secret-123"

    def test_non_string_sensitive_values_are_round_tripped_via_json(self):
        a = AnswerFactory()
        a.set_value(17, sensitive=True)
        a.save()
        a.refresh_from_db()
        # Decryption returns the JSON string; this is the documented behaviour.
        # Callers that need typed output should interpret by field type.
        assert a.value == "17"


@pytest.mark.django_db
class TestRedactedValue:
    def test_admin_sees_plaintext(self):
        a = AnswerFactory()
        a.set_value("top-secret", sensitive=True)
        a.save()
        assert a.redacted_value(Membership.Role.ADMIN) == "top-secret"

    def test_analyst_sees_placeholder(self):
        a = AnswerFactory()
        a.set_value("top-secret", sensitive=True)
        a.save()
        assert a.redacted_value(Membership.Role.ANALYST) == "[encrypted]"
        assert a.redacted_value(Membership.Role.VIEWER) == "[encrypted]"

    def test_non_sensitive_value_not_redacted_for_anyone(self):
        a = AnswerFactory()
        a.set_value("hello", sensitive=False)
        a.save()
        assert a.redacted_value(Membership.Role.ADMIN) == "hello"
        assert a.redacted_value(Membership.Role.ANALYST) == "hello"
