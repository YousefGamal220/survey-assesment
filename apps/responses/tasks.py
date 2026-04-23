"""Async tasks — report generation, CSV export, bulk invitations.

These run via Celery + Redis in production; test settings set
CELERY_TASK_ALWAYS_EAGER so they execute synchronously under pytest.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

from celery import shared_task

from apps.responses.models import Answer, Response

logger = logging.getLogger(__name__)


@shared_task(name="responses.export_survey_csv")
def export_survey_csv(survey_id: str) -> str:
    """Build a CSV of every submitted response for the given survey.

    Returns the CSV as a string (callers write it to S3/object storage).
    Per-cell encryption stays encrypted in the export — analysts must use
    the API (which decrypts based on role) if they need plaintext.
    """
    from apps.surveys.models import Field, Survey

    survey = Survey.all_objects.get(id=survey_id)
    fields = list(
        Field.all_objects.filter(section__survey=survey).order_by("section__position", "position")
    )
    field_keys = [f.key for f in fields]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["response_id", "submitted_at", "respondent_email", *field_keys])

    submitted = list(
        Response.all_objects.filter(survey=survey, status=Response.Status.SUBMITTED)
        .select_related("respondent")
        .order_by("submitted_at")
    )
    # Batch-fetch answers cross-tenant (all_objects) — the response FK already
    # scopes them to this survey. Celery workers run without a tenant context,
    # so we can't use the default TenantManager here.
    answer_rows = Answer.all_objects.filter(response__in=submitted)
    by_response: dict[Any, dict[str, Answer]] = {}
    for row_ in answer_rows:
        by_response.setdefault(row_.response_id, {})[row_.field_key] = row_

    for r in submitted:
        answers_by_key = by_response.get(r.id, {})
        row: list[Any] = [
            str(r.id),
            r.submitted_at.isoformat() if r.submitted_at else "",
            r.respondent.email if r.respondent else "",
        ]
        for k in field_keys:
            a = answers_by_key.get(k)
            if a is None:
                row.append("")
            elif a.value_encrypted is not None:
                row.append("[encrypted]")
            else:
                row.append(a.value_json)
        writer.writerow(row)

    result = buf.getvalue()
    logger.info(
        "export_survey_csv",
        extra={"survey_id": str(survey_id), "rows": len(submitted)},
    )
    return result


@shared_task(name="responses.aggregate_response_counts")
def aggregate_response_counts(survey_id: str) -> dict[str, int]:
    """Return {draft: N, submitted: N} for a survey. Used by analytics dashboards."""
    qs = Response.all_objects.filter(survey_id=survey_id)
    draft = qs.filter(status=Response.Status.DRAFT).count()
    submitted = qs.filter(status=Response.Status.SUBMITTED).count()
    return {"draft": draft, "submitted": submitted}


@shared_task(name="responses.send_bulk_invitations")
def send_bulk_invitations(survey_id: str, emails: list[str]) -> int:
    """Fan-out stub for survey invitations.

    In a real deployment this would call an email adapter (SES, Postmark). For
    the take-home scope we log + return the count so the wiring is demonstrable
    under the Celery + pytest-eager setup.
    """
    logger.info(
        "send_bulk_invitations",
        extra={"survey_id": str(survey_id), "recipients": len(emails)},
    )
    return len(emails)


@shared_task(name="responses.per_field_answer_histogram")
def per_field_answer_histogram(survey_id: str, field_key: str) -> dict[str, int]:
    """Count occurrences of each plaintext value for a non-sensitive field.
    Returns {} if the field is encrypted (nothing to aggregate in plaintext)."""
    values = Answer.all_objects.filter(
        response__survey_id=survey_id,
        response__status=Response.Status.SUBMITTED,
        field_key=field_key,
        value_encrypted__isnull=True,
    ).values_list("value_json", flat=True)

    hist: dict[str, int] = {}
    for v in values:
        key = str(v)
        hist[key] = hist.get(key, 0) + 1
    return hist
