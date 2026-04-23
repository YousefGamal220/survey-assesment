from __future__ import annotations

import uuid
from typing import Any

from django.db import models

from apps.accounts.models import Membership
from apps.core.models import TenantScopedModel
from apps.responses.crypto import decrypt, encrypt


class Response(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey = models.ForeignKey(
        "surveys.Survey",
        on_delete=models.PROTECT,
        related_name="responses",
    )
    respondent = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "responses_response"
        ordering = ["-started_at"]
        constraints = [
            # Exactly one draft per (org, survey, respondent). Submitted rows
            # are not dedup'd — a user may submit twice if the survey permits.
            models.UniqueConstraint(
                fields=["organization", "survey", "respondent"],
                condition=models.Q(status="draft"),
                name="uniq_draft_per_survey_respondent",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "survey", "status"]),
            models.Index(fields=["organization", "submitted_at"]),
        ]

    def __str__(self) -> str:
        return f"Response({self.survey_id}, {self.respondent_id}, {self.status})"


class Answer(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="answers")
    field_key = models.CharField(max_length=64, db_index=True)

    # Exactly one of value_json / value_encrypted is populated per row.
    # DJ001 is suppressed: NULL here is semantic — "not this variant" — so the
    # usual "" default for TextField would corrupt the dispatch in `.value`.
    value_json = models.JSONField(null=True, blank=True)
    value_encrypted = models.TextField(null=True, blank=True)  # noqa: DJ001

    class Meta:
        db_table = "responses_answer"
        ordering = ["response_id", "field_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["response", "field_key"],
                name="uniq_answer_per_response_key",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "field_key"]),
        ]

    # ------------------------------------------------------------------
    # Encryption dispatch
    # ------------------------------------------------------------------
    @property
    def value(self) -> Any:
        """Return the plain Python value, decrypting if needed."""
        if self.value_encrypted is not None:
            return decrypt(self.value_encrypted)
        return self.value_json

    def set_value(self, value: Any, *, sensitive: bool) -> None:
        """Write the value into the correct column based on the sensitivity flag."""
        if sensitive:
            # Encrypted column holds a string — coerce non-string sensitive values
            # (e.g. an int age) through JSON so round-trip stays lossless.
            import json

            payload = value if isinstance(value, str) else json.dumps(value)
            self.value_encrypted = encrypt(payload)
            self.value_json = None
        else:
            self.value_json = value
            self.value_encrypted = None

    def redacted_value(self, role: str) -> Any:
        """Role-aware read-path: analyst/viewer see a redaction token instead
        of decrypted sensitive data."""
        if self.value_encrypted is None:
            return self.value_json
        if role == Membership.Role.ADMIN:
            return self.value
        return "[encrypted]"

    def __str__(self) -> str:
        return f"{self.field_key}"
