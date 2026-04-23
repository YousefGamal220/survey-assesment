from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOrgAdmin, IsOrgAnalyst
from apps.surveys.models import Field, Section, Survey
from apps.surveys.serializers import SurveySerializer


_SURVEY_EXAMPLE = OpenApiExample(
    "Employment survey with conditional logic",
    value={
        "title": "Employment survey",
        "description": "Pilot v1",
        "sections": [
            {
                "position": 0,
                "title": "Basics",
                "fields": [
                    {
                        "key": "employed",
                        "position": 0,
                        "type": "single_choice",
                        "label": "Are you employed?",
                        "required": True,
                        "config": {
                            "choices": [
                                {"value": "yes", "label": "Yes"},
                                {"value": "no", "label": "No"},
                            ]
                        },
                    }
                ],
            },
            {
                "position": 1,
                "title": "Company details",
                "visible_when": {"field": "employed", "op": "eq", "value": "yes"},
                "fields": [
                    {
                        "key": "company_name",
                        "position": 0,
                        "type": "short_text",
                        "label": "Company",
                        "required": True,
                    },
                    {
                        "key": "annual_income",
                        "position": 1,
                        "type": "number",
                        "label": "Annual income (USD)",
                        "config": {"sensitive": True, "min": 0},
                    },
                ],
            },
        ],
    },
    request_only=True,
)


@extend_schema_view(
    create=extend_schema(
        tags=["surveys"],
        summary="Create a draft survey (admin). Body is the full nested tree.",
        examples=[_SURVEY_EXAMPLE],
    ),
    update=extend_schema(
        tags=["surveys"],
        summary="Replace the draft tree (draft status only).",
        examples=[_SURVEY_EXAMPLE],
    ),
    partial_update=extend_schema(
        tags=["surveys"],
        summary="Patch draft (same full-tree semantics as PUT).",
        examples=[_SURVEY_EXAMPLE],
    ),
    list=extend_schema(tags=["surveys"], summary="List surveys (analyst+)."),
    retrieve=extend_schema(tags=["surveys"], summary="Retrieve nested survey by id."),
    destroy=extend_schema(tags=["surveys"], summary="Soft-archive a survey."),
)
class SurveyViewSet(viewsets.ModelViewSet):
    serializer_class = SurveySerializer
    lookup_field = "id"

    def get_queryset(self):
        qs = Survey.objects.all().prefetch_related("sections__fields")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_permissions(self):
        if self.action in {"list", "retrieve", "latest"}:
            return [IsOrgAnalyst()]
        return [IsOrgAdmin()]

    def destroy(self, request, *args, **kwargs):
        survey = self.get_object()
        survey.status = Survey.Status.ARCHIVED
        survey.save(update_fields=["status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["surveys"],
        summary="Latest version per survey_group_id.",
        responses=SurveySerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="latest")
    def latest(self, request):
        """List only the newest version per survey_group_id."""
        qs = self.get_queryset()
        pairs = set(
            qs.values("survey_group_id")
            .annotate(max_v=Max("version"))
            .values_list("survey_group_id", "max_v")
        )
        matching = [s for s in qs if (s.survey_group_id, s.version) in pairs]
        page: list | None = self.paginate_queryset(matching)  # type: ignore[arg-type]
        ser = self.get_serializer(page if page is not None else matching, many=True)
        if page is not None:
            return self.get_paginated_response(ser.data)
        return Response(ser.data)

    @extend_schema(
        tags=["surveys"],
        summary="Publish a draft survey. Idempotent-safe: returns 409 if already published.",
        request=None,
        responses={200: SurveySerializer, 409: None},
    )
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def publish(self, request, id=None):
        survey = self.get_object()
        if survey.status != Survey.Status.DRAFT:
            return Response(
                {"detail": "only draft surveys can be published"},
                status=status.HTTP_409_CONFLICT,
            )
        survey.status = Survey.Status.PUBLISHED
        survey.published_at = timezone.now()
        survey.save(update_fields=["status", "published_at", "updated_at"])
        return Response(self.get_serializer(survey).data)

    @extend_schema(
        tags=["surveys"],
        summary="Clone a published survey into a new draft (version = N+1, shared survey_group_id).",
        request=None,
        responses={201: SurveySerializer, 409: None},
    )
    @action(detail=True, methods=["post"], url_path="new_version")
    @transaction.atomic
    def new_version(self, request, id=None):
        source = self.get_object()
        if source.status != Survey.Status.PUBLISHED:
            return Response(
                {"detail": "only published surveys can fork a new version"},
                status=status.HTTP_409_CONFLICT,
            )

        next_version = (
            Survey.objects.filter(
                organization=source.organization,
                survey_group_id=source.survey_group_id,
            ).aggregate(Max("version"))["version__max"]
            or 0
        ) + 1

        clone = Survey.all_objects.create(
            organization=source.organization,
            survey_group_id=source.survey_group_id,
            version=next_version,
            title=source.title,
            description=source.description,
            status=Survey.Status.DRAFT,
            created_by=request.user,
        )
        for sec in source.sections.all().prefetch_related("fields"):
            new_sec = Section.all_objects.create(
                organization=clone.organization,
                survey=clone,
                position=sec.position,
                title=sec.title,
                description=sec.description,
                visible_when=sec.visible_when,
            )
            for fld in sec.fields.all():
                Field.all_objects.create(
                    organization=clone.organization,
                    section=new_sec,
                    key=fld.key,
                    position=fld.position,
                    type=fld.type,
                    label=fld.label,
                    help_text=fld.help_text,
                    required=fld.required,
                    config=fld.config,
                    visible_when=fld.visible_when,
                )
        return Response(self.get_serializer(clone).data, status=status.HTTP_201_CREATED)
