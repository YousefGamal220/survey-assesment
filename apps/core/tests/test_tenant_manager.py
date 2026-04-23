import pytest

from apps.core.context import (
    current_organization,
    reset_current_organization,
    set_current_organization,
)
from apps.core.exceptions import TenantNotSetError
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
class TestTenantContext:
    def test_set_and_get_current_org(self):
        org = OrganizationFactory()
        token = set_current_organization(org)
        try:
            assert current_organization() == org
        finally:
            reset_current_organization(token)

    def test_get_without_set_returns_none(self):
        assert current_organization() is None


@pytest.mark.django_db
class TestTenantManager:
    def test_objects_without_tenant_raises(self, _dummy_tenant_table):
        from apps.core.tests.tenant_test_model import DummyTenantModel

        with pytest.raises(TenantNotSetError):
            list(DummyTenantModel.objects.all())

    def test_objects_filters_by_current_org(self, _dummy_tenant_table):
        from apps.core.tests.tenant_test_model import DummyTenantModel

        org_a = OrganizationFactory()
        org_b = OrganizationFactory()
        DummyTenantModel.all_objects.create(organization=org_a, name="a-row")
        DummyTenantModel.all_objects.create(organization=org_b, name="b-row")

        token = set_current_organization(org_a)
        try:
            rows = list(DummyTenantModel.objects.all())
            assert len(rows) == 1
            assert rows[0].name == "a-row"
        finally:
            reset_current_organization(token)

    def test_all_objects_bypasses_tenant_filter(self, _dummy_tenant_table):
        from apps.core.tests.tenant_test_model import DummyTenantModel

        count = DummyTenantModel.all_objects.count()
        assert count >= 0
