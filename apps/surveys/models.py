from __future__ import annotations

import uuid

from django.db import models

from apps.core.models import TenantScopedModel


class Survey(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey_group_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "surveys_survey"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "survey_group_id", "version"],
                name="uniq_survey_group_version",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "survey_group_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} v{self.version} ({self.status})"


class Section(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="sections")
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    visible_when = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "surveys_section"
        ordering = ["survey_id", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "position"],
                name="uniq_section_survey_position",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.survey_id}#{self.position} {self.title}"


class Field(TenantScopedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(max_length=64)
    position = models.PositiveIntegerField()
    type = models.CharField(max_length=32)
    label = models.CharField(max_length=200)
    help_text = models.TextField(blank=True, default="")
    required = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    visible_when = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "surveys_field"
        ordering = ["section_id", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "position"],
                name="uniq_field_section_position",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.section_id}.{self.key} ({self.type})"
