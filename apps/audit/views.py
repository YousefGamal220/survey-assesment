from __future__ import annotations

from rest_framework import serializers, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from apps.audit.models import AuditLog
from apps.core.permissions import IsOrgAnalyst


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_email",
            "role",
            "method",
            "path",
            "status_code",
            "request_id",
            "extra",
            "created_at",
        ]
        read_only_fields = fields


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Analyst+ can browse audit rows for their own org, filterable by
    ?user=<id>, ?method=<GET|POST|...>, ?path_contains=<substr>."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsOrgAnalyst]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        # request.organization is attached at runtime by TenantAuthentication.
        qs = AuditLog.objects.filter(organization=self.request.organization)  # type: ignore[attr-defined]
        params = self.request.query_params
        if user_id := params.get("user"):
            qs = qs.filter(user_id=user_id)
        if method := params.get("method"):
            qs = qs.filter(method=method.upper())
        if needle := params.get("path_contains"):
            qs = qs.filter(path__icontains=needle)
        return qs.order_by("-created_at")
