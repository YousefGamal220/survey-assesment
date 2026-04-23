"""Test-only model used to exercise TenantManager end-to-end.

Not registered in any migration — we create the table inline via a pytest
fixture. Kept under `tests/` so it never ships.
"""

from __future__ import annotations

from django.db import connection, models

from apps.core.managers import TenantManager


class DummyTenantModel(models.Model):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        app_label = "core"
        db_table = "core_dummy_tenant_model"
        managed = False


def ensure_table() -> None:
    """Create the table if missing — called from the test fixture."""
    existing = connection.introspection.table_names()
    if DummyTenantModel._meta.db_table in existing:
        return
    with connection.schema_editor() as schema_editor:
        schema_editor.create_model(DummyTenantModel)
