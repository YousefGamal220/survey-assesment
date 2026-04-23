from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from apps.surveys.field_types import all_field_type_names, get_field_type
from apps.surveys.logic import evaluate
from apps.surveys.models import Field, Section, Survey


class _RuleField(serializers.JSONField):
    """A JSONField that structurally validates the visible_when DSL."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise serializers.ValidationError("visible_when must be a JSON object")
        evaluate(value, {})  # raises ValidationError on bad shape
        return value


class FieldSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    type = serializers.ChoiceField(choices=all_field_type_names())
    config = serializers.JSONField(required=False)
    visible_when = _RuleField(required=False, allow_null=True)

    class Meta:
        model = Field
        fields = [
            "id",
            "key",
            "position",
            "type",
            "label",
            "help_text",
            "required",
            "config",
            "visible_when",
        ]

    def validate(self, attrs):
        field_type = get_field_type(attrs["type"])
        field_type.validate_config(attrs.get("config") or {})
        return attrs


class SectionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    fields = FieldSerializer(many=True, required=False)  # type: ignore[assignment]
    visible_when = _RuleField(required=False, allow_null=True)

    class Meta:
        model = Section
        fields = ["id", "position", "title", "description", "visible_when", "fields"]


class SurveySerializer(serializers.ModelSerializer):
    sections = SectionSerializer(many=True, required=False)

    class Meta:
        model = Survey
        fields = [
            "id",
            "survey_group_id",
            "version",
            "title",
            "description",
            "status",
            "published_at",
            "created_at",
            "updated_at",
            "sections",
        ]
        read_only_fields = [
            "id",
            "survey_group_id",
            "version",
            "status",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        sections = attrs.get("sections", [])
        keys: set[str] = set()
        for sec in sections:
            for fld in sec.get("fields", []):
                if fld["key"] in keys:
                    raise serializers.ValidationError(
                        {"fields": f"duplicate key: {fld['key']!r} (must be unique per survey)"}
                    )
                keys.add(fld["key"])
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        sections_data = validated_data.pop("sections", [])
        organization = self.context["request"].organization
        validated_data["organization"] = organization
        validated_data["created_by"] = self.context["request"].user
        survey = Survey.all_objects.create(**validated_data)
        self._write_tree(survey, sections_data)
        return survey

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != Survey.Status.DRAFT:
            raise serializers.ValidationError({"status": "only draft surveys can be edited"})
        sections_data = validated_data.pop("sections", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if sections_data is not None:
            Section.all_objects.filter(survey=instance).delete()
            self._write_tree(instance, sections_data)
        return instance

    def _write_tree(self, survey: Survey, sections_data: list[dict]) -> None:
        for sec in sections_data:
            fields_data = sec.pop("fields", [])
            sec.pop("id", None)
            section = Section.all_objects.create(
                organization=survey.organization, survey=survey, **sec
            )
            for fld in fields_data:
                fld.pop("id", None)
                Field.all_objects.create(organization=survey.organization, section=section, **fld)
