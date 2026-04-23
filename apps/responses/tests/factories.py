from __future__ import annotations

import factory

from apps.accounts.tests.factories import UserFactory
from apps.responses.models import Answer, Response
from apps.surveys.tests.factories import SurveyFactory


class _TenantBypassFactory(factory.django.DjangoModelFactory):
    """Same tenant-bypass pattern as surveys — tests don't sit behind the
    TenantAuthentication middleware, so route factory writes through all_objects."""

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class.all_objects.create(*args, **kwargs)


class ResponseFactory(_TenantBypassFactory):
    class Meta:
        model = Response

    organization = factory.SelfAttribute("survey.organization")
    survey = factory.SubFactory(SurveyFactory)
    respondent = factory.SubFactory(UserFactory)
    status = Response.Status.DRAFT


class AnswerFactory(_TenantBypassFactory):
    class Meta:
        model = Answer

    organization = factory.SelfAttribute("response.organization")
    response = factory.SubFactory(ResponseFactory)
    field_key = factory.Sequence(lambda n: f"q_{n}")
    value_json = "sample answer"
