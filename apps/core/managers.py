from __future__ import annotations

from django.db import models

from apps.core.context import current_organization
from apps.core.exceptions import TenantNotSetError


class TenantManager(models.Manager):
    """Default manager for tenant-scoped models.

    Filters every query by the current tenant. Raises if no tenant is set —
    failing loud beats silently leaking cross-tenant data.
    """

    def get_queryset(self) -> models.QuerySet:
        org = current_organization()
        if org is None:
            raise TenantNotSetError(
                f"{self.model.__name__}.objects accessed without tenant context; "
                "use .all_objects for cross-tenant access"
            )
        return super().get_queryset().filter(organization=org)
