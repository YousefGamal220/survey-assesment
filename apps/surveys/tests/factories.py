from __future__ import annotations

import factory

from apps.organizations.tests.factories import OrganizationFactory
from apps.surveys.models import Field, Section, Survey


class _TenantBypassFactory(factory.django.DjangoModelFactory):
    """Tenant-scoped models guard `objects` with a contextvar, which isn't set in
    unit tests. Route factory writes through `all_objects` so tests don't need
    a per-case tenant fixture."""

    class Meta:
        abstract = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class.all_objects.create(*args, **kwargs)


class SurveyFactory(_TenantBypassFactory):
    class Meta:
        model = Survey

    organization = factory.SubFactory(OrganizationFactory)
    title = factory.Sequence(lambda n: f"Survey {n}")
    description = ""
    status = Survey.Status.DRAFT


class SectionFactory(_TenantBypassFactory):
    class Meta:
        model = Section

    organization = factory.SelfAttribute("survey.organization")
    survey = factory.SubFactory(SurveyFactory)
    position = factory.Sequence(lambda n: n)
    title = factory.Sequence(lambda n: f"Section {n}")


class FieldFactory(_TenantBypassFactory):
    class Meta:
        model = Field

    organization = factory.SelfAttribute("section.organization")
    section = factory.SubFactory(SectionFactory)
    key = factory.Sequence(lambda n: f"field_{n}")
    position = factory.Sequence(lambda n: n)
    type = "short_text"
    label = factory.Sequence(lambda n: f"Field {n}")
    required = False
    config = {}
