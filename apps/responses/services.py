"""Response lifecycle services — pure functions, transaction-safe, no HTTP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.responses.models import Answer, Response
from apps.responses.signals import SURVEY_CACHE_KEY, SURVEY_CACHE_TTL
from apps.surveys.field_types import get_field_type, is_sensitive
from apps.surveys.logic import evaluate
from apps.surveys.models import Field, Survey


class ResponseValidationError(ValidationError):
    """Raised when a submission fails server-side validation. The payload is
    a `{field_key: [error, ...]}` dict that the DRF exception handler maps to
    the standard envelope."""


def upsert_draft_answers(response: Response, answers: Mapping[str, Any]) -> None:
    """Merge `{field_key: value}` into the draft's Answer rows.

    Unknown keys are accepted at draft time — they're filtered/validated on submit.
    Sensitivity is read from the current survey config so the correct column is
    populated per key.
    """
    if response.status != Response.Status.DRAFT:
        raise ValidationError({"status": "only draft responses are editable"})

    survey = response.survey
    sensitivity = _field_sensitivity_map(survey)

    with transaction.atomic():
        for key, value in answers.items():
            sensitive = sensitivity.get(key, False)
            row = Answer.all_objects.filter(response=response, field_key=key).first()
            if row is None:
                row = Answer(
                    organization=response.organization,
                    response=response,
                    field_key=key,
                )
            row.set_value(value, sensitive=sensitive)
            row.save()


def submit_response(response: Response) -> Response:
    """Validate, lock, and timestamp a draft response.

    Validation rules (all must pass before anything persists):
      1. No unknown field keys in answers
      2. For each `required` field: must be visible AND have a non-empty answer
      3. For each answer: must pass its type's `validate_answer`, evaluated only
         when the field is visible under the current answer set

    Raises `ResponseValidationError` with a `{field_key: [...]}` payload; on
    success flips status to submitted and returns the refreshed row.
    """
    if response.status != Response.Status.DRAFT:
        raise ValidationError({"status": "response already submitted"})

    survey: Survey = response.survey
    fields_by_key: dict[str, Field] = {
        f.key: f for f in Field.all_objects.filter(section__survey=survey)
    }

    # Gather answer dict for logic evaluation and cross-check
    answers_qs = Answer.all_objects.filter(response=response).select_related()
    answers: dict[str, Any] = {a.field_key: a.value for a in answers_qs}

    errors: dict[str, list[str]] = {}

    # Rule 1: unknown keys
    unknown = set(answers) - set(fields_by_key)
    for k in unknown:
        errors.setdefault(k, []).append("unknown field key")

    # Rule 2 + 3: per-field validation, gated by visible_when
    for key, field in fields_by_key.items():
        try:
            visible = _field_visible(field, answers)
        except ValidationError as exc:
            errors.setdefault(key, []).append(f"visible_when rule error: {exc.detail}")
            continue

        if not visible:
            continue

        if key not in answers or _is_empty(answers[key]):
            if field.required:
                errors.setdefault(key, []).append("this field is required")
            continue

        try:
            get_field_type(field.type).validate_answer(answers[key], field.config or {})
        except ValidationError as exc:
            errors.setdefault(key, []).append(str(exc.detail))

    if errors:
        raise ResponseValidationError(errors)

    with transaction.atomic():
        response.status = Response.Status.SUBMITTED
        response.submitted_at = timezone.now()
        response.save(update_fields=["status", "submitted_at", "updated_at"])

    response.refresh_from_db()
    return response


# ----------------------------------------------------------------------
# Cached survey read (bucket 3 — performance)
# ----------------------------------------------------------------------
def get_cached_survey_payload(survey_id) -> dict | None:
    """Read the nested survey tree from Redis, populate on miss.

    The payload is a plain dict — whatever the caller serialized — keyed on
    survey_id only. Invalidation lives in apps.responses.signals.
    """
    key = SURVEY_CACHE_KEY.format(id=survey_id)
    hit = cache.get(key)
    if hit is not None:
        return hit
    return None


def cache_survey_payload(survey_id, payload: dict) -> None:
    cache.set(SURVEY_CACHE_KEY.format(id=survey_id), payload, timeout=SURVEY_CACHE_TTL)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _field_sensitivity_map(survey: Survey) -> dict[str, bool]:
    return {f.key: is_sensitive(f.config) for f in Field.all_objects.filter(section__survey=survey)}


def _field_visible(field: Field, answers: Mapping[str, Any]) -> bool:
    """A field is visible iff both its section AND the field's own visible_when
    evaluate truthy (or are None, which evaluates truthy)."""
    if not evaluate(field.section.visible_when, dict(answers)):
        return False
    return evaluate(field.visible_when, dict(answers))


def _is_empty(value: Any) -> bool:
    """Mirror the logic engine's `is_set` semantics: "", None, and empty lists
    are treated as unanswered. Numeric 0 and False are valid answers."""
    if value is None or value == "":
        return True
    return isinstance(value, list) and len(value) == 0
