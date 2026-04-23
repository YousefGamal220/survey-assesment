"""Cache invalidation wiring.

When a Survey row changes (publish, new_version, admin edit), the cached
nested read used by the respondent flow must be invalidated so the next
fetch sees the new structure.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

SURVEY_CACHE_KEY = "survey:nested:{id}"
SURVEY_CACHE_TTL = 60  # seconds


def _key(survey_id) -> str:
    return SURVEY_CACHE_KEY.format(id=survey_id)


def invalidate_survey(survey_id) -> None:
    cache.delete(_key(survey_id))


@receiver(post_save, sender="surveys.Survey")
def _invalidate_on_survey_save(sender, instance, **kwargs):
    invalidate_survey(instance.id)


@receiver(post_delete, sender="surveys.Survey")
def _invalidate_on_survey_delete(sender, instance, **kwargs):
    invalidate_survey(instance.id)


@receiver(post_save, sender="surveys.Section")
def _invalidate_on_section_save(sender, instance, **kwargs):
    invalidate_survey(instance.survey_id)


@receiver(post_delete, sender="surveys.Section")
def _invalidate_on_section_delete(sender, instance, **kwargs):
    invalidate_survey(instance.survey_id)


@receiver(post_save, sender="surveys.Field")
def _invalidate_on_field_save(sender, instance, **kwargs):
    # section_id is already populated; the extra lookup is cheap and
    # the whole cache entry is keyed by survey_id anyway.
    invalidate_survey(instance.section.survey_id)


@receiver(post_delete, sender="surveys.Field")
def _invalidate_on_field_delete(sender, instance, **kwargs):
    invalidate_survey(instance.section.survey_id)
