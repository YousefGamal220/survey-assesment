from __future__ import annotations

from django.db import models

from apps.core.managers import TenantManager


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScopedModel(TimestampedModel):
    """Abstract base: every tenant-owned model inherits from this.

    - `objects` is the tenant-filtering manager (raises if no tenant set).
    - `all_objects` escapes the filter (admin, migrations, cross-tenant celery tasks).
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
