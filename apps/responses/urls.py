from __future__ import annotations

from django.urls import path

from apps.responses.views import MyResponsesView, ResponseViewSet

app_name = "responses"

# Nested routing is hand-rolled (no drf-nested-routers dep):
#   /surveys/{survey_id}/responses/
#   /surveys/{survey_id}/responses/{id}/
#   /surveys/{survey_id}/responses/{id}/submit/
#   /responses/mine/
_list = ResponseViewSet.as_view({"get": "list", "post": "create"})
_detail = ResponseViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
)
_submit = ResponseViewSet.as_view({"post": "submit"})

urlpatterns = [
    path("surveys/<uuid:survey_id>/responses/", _list, name="list"),
    path("surveys/<uuid:survey_id>/responses/<uuid:id>/", _detail, name="detail"),
    path(
        "surveys/<uuid:survey_id>/responses/<uuid:id>/submit/",
        _submit,
        name="submit",
    ),
    path("responses/mine/", MyResponsesView.as_view(), name="mine"),
]
