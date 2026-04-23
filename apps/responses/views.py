from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response as DRFResponse
from rest_framework.views import APIView

from apps.core.permissions import IsOrgAnalyst
from apps.responses.models import Response
from apps.responses.permissions import IsOwnerOrAnalystReader
from apps.responses.serializers import (
    AnswersPayloadSerializer,
    ResponseDetailSerializer,
    ResponseListSerializer,
)
from apps.responses.services import submit_response, upsert_draft_answers
from apps.surveys.models import Survey


_SURVEY_ID = OpenApiParameter(
    name="survey_id",
    location=OpenApiParameter.PATH,
    type={"type": "string", "format": "uuid"},
    required=True,
    description="UUID of the parent survey.",
)


@extend_schema(tags=["responses"], parameters=[_SURVEY_ID])
class ResponseViewSet(viewsets.ViewSet):
    """Nested under /surveys/{survey_id}/responses/."""

    lookup_field = "id"

    def get_permissions(self):
        if self.action == "list":
            return [IsAuthenticated(), IsOrgAnalyst()]
        return [IsAuthenticated(), IsOwnerOrAnalystReader()]

    # ---------- Helpers ----------
    def _get_survey(self, survey_id: str | None) -> Survey:
        return get_object_or_404(Survey.objects.all(), id=survey_id)

    def _get_response(self, survey: Survey, id: str | None) -> Response:
        obj = get_object_or_404(
            Response.objects.filter(survey=survey).select_related("respondent"),
            id=id,
        )
        self.check_object_permissions(self.request, obj)
        return obj

    # ---------- list ----------
    @extend_schema(
        summary="List submitted responses for a survey (analyst+).",
        responses=ResponseListSerializer(many=True),
    )
    def list(self, request, survey_id: str | None = None):
        survey = self._get_survey(survey_id)
        qs = (
            Response.objects.filter(survey=survey, status=Response.Status.SUBMITTED)
            .select_related("respondent")
            .prefetch_related("answers")
            .order_by("-submitted_at")
        )
        ser = ResponseListSerializer(qs, many=True, context={"request": request})
        return DRFResponse({"count": qs.count(), "results": ser.data})

    # ---------- create (idempotent draft) ----------
    @extend_schema(
        summary="Start (or resume) a draft response. Idempotent per respondent.",
        request=None,
        responses={200: ResponseDetailSerializer, 201: ResponseDetailSerializer},
    )
    def create(self, request, survey_id: str | None = None):
        survey = self._get_survey(survey_id)
        existing = Response.objects.filter(
            survey=survey,
            respondent=request.user,
            status=Response.Status.DRAFT,
        ).first()
        if existing is not None:
            ser = ResponseDetailSerializer(existing, context={"request": request})
            return DRFResponse(ser.data, status=status.HTTP_200_OK)

        draft = Response.all_objects.create(
            organization=request.organization,
            survey=survey,
            respondent=request.user,
            status=Response.Status.DRAFT,
        )
        ser = ResponseDetailSerializer(draft, context={"request": request})
        return DRFResponse(ser.data, status=status.HTTP_201_CREATED)

    # ---------- retrieve ----------
    @extend_schema(
        summary="Retrieve a response (owner or analyst+).",
        responses=ResponseDetailSerializer,
    )
    def retrieve(self, request, survey_id: str | None = None, id: str | None = None):
        survey = self._get_survey(survey_id)
        obj = self._get_response(survey, id)
        ser = ResponseDetailSerializer(obj, context={"request": request})
        return DRFResponse(ser.data)

    # ---------- partial_update: patch answers ----------
    @extend_schema(
        summary="Merge {field_key: value} pairs into a draft (owner only).",
        request=AnswersPayloadSerializer,
        responses=ResponseDetailSerializer,
        examples=[
            OpenApiExample(
                "save progress",
                value={"answers": {"employment_status": "full_time", "years_experience": 7}},
                request_only=True,
            ),
        ],
    )
    def partial_update(self, request, survey_id: str | None = None, id: str | None = None):
        survey = self._get_survey(survey_id)
        obj = self._get_response(survey, id)
        if obj.respondent_id != request.user.pk:
            raise PermissionDenied("only the owner can edit a draft")

        ser = AnswersPayloadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        upsert_draft_answers(obj, ser.validated_data["answers"])
        refreshed = ResponseDetailSerializer(obj, context={"request": request})
        return DRFResponse(refreshed.data)

    # ---------- destroy ----------
    @extend_schema(
        summary="Delete own draft (submitted responses are immutable).",
        request=None,
        responses={204: None},
    )
    def destroy(self, request, survey_id: str | None = None, id: str | None = None):
        survey = self._get_survey(survey_id)
        obj = self._get_response(survey, id)
        if obj.respondent_id != request.user.pk:
            raise PermissionDenied("only the owner can delete their draft")
        if obj.status != Response.Status.DRAFT:
            raise PermissionDenied("submitted responses cannot be deleted")
        obj.delete()
        return DRFResponse(status=status.HTTP_204_NO_CONTENT)

    # ---------- submit ----------
    @extend_schema(
        summary="Lock the draft. Runs full server-side validation: required gated by visible_when, per-type checks.",
        request=None,
        responses={200: ResponseDetailSerializer, 400: None, 403: None},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, survey_id: str | None = None, id: str | None = None):
        survey = self._get_survey(survey_id)
        obj = self._get_response(survey, id)
        if obj.respondent_id != request.user.pk:
            raise PermissionDenied("only the owner can submit their response")
        submit_response(obj)
        ser = ResponseDetailSerializer(obj, context={"request": request})
        return DRFResponse(ser.data)


@extend_schema(
    tags=["responses"],
    summary="Caller's own responses across every survey in the current tenant.",
    responses=ResponseListSerializer(many=True),
)
class MyResponsesView(APIView):
    """GET /api/v1/responses/mine/ — the caller's own responses across every
    survey in the current tenant."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = (
            Response.objects.filter(respondent=request.user)
            .select_related("survey")
            .order_by("-started_at")
        )
        ser = ResponseListSerializer(qs, many=True, context={"request": request})
        return DRFResponse({"count": qs.count(), "results": ser.data})
