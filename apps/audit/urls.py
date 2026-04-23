from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.audit.views import AuditLogViewSet

app_name = "audit"

router = DefaultRouter()
router.register(r"audit-log", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
