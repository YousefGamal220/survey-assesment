from __future__ import annotations

from rest_framework.routers import DefaultRouter

from apps.surveys.views import SurveyViewSet

app_name = "surveys"

router = DefaultRouter()
router.register(r"surveys", SurveyViewSet, basename="survey")

urlpatterns = router.urls
