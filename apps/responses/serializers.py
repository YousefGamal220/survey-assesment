from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import Membership
from apps.responses.models import Answer, Response


class AnswerSerializer(serializers.Serializer):
    """Role-aware answer representation. On read, sensitive answers are
    redacted for non-admins. On write (draft patching), callers send the
    same `{key, value}` shape and the service layer handles encryption."""

    field_key = serializers.CharField(max_length=64)
    value = serializers.JSONField()

    def to_representation(self, instance: Answer):
        role = _role_from_context(self.context)
        return {"field_key": instance.field_key, "value": instance.redacted_value(role)}


class ResponseListSerializer(serializers.ModelSerializer):
    respondent_email = serializers.EmailField(source="respondent.email", read_only=True)

    class Meta:
        model = Response
        fields = [
            "id",
            "survey",
            "respondent",
            "respondent_email",
            "status",
            "started_at",
            "submitted_at",
        ]


class ResponseDetailSerializer(serializers.ModelSerializer):
    respondent_email = serializers.EmailField(source="respondent.email", read_only=True)
    answers = serializers.SerializerMethodField()

    class Meta:
        model = Response
        fields = [
            "id",
            "survey",
            "respondent",
            "respondent_email",
            "status",
            "started_at",
            "submitted_at",
            "answers",
        ]

    def get_answers(self, obj: Response) -> list[dict]:
        role = _role_from_context(self.context)
        return [
            {"field_key": a.field_key, "value": a.redacted_value(role)} for a in obj.answers.all()
        ]


class AnswersPayloadSerializer(serializers.Serializer):
    """Body of PATCH /responses/{id}/ — a dict of {field_key: value}."""

    answers = serializers.DictField(child=serializers.JSONField())


def _role_from_context(ctx: dict) -> str:
    request = ctx.get("request")
    if request is None:
        return Membership.Role.VIEWER
    membership = getattr(request, "membership", None)
    return getattr(membership, "role", Membership.Role.VIEWER)
