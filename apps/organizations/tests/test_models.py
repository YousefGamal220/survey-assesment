import pytest
from django.db import IntegrityError

from apps.organizations.models import Organization
from apps.organizations.tests.factories import OrganizationFactory


@pytest.mark.django_db
class TestOrganization:
    def test_basic_creation(self):
        org = OrganizationFactory(name="Acme", slug="acme")
        assert org.name == "Acme"
        assert org.slug == "acme"
        assert org.is_active is True
        assert org.id is not None
        assert org.created_at is not None

    def test_slug_unique(self):
        OrganizationFactory(slug="dup")
        with pytest.raises(IntegrityError):
            Organization.objects.create(name="x", slug="dup")

    def test_str(self):
        assert str(OrganizationFactory(name="Acme")) == "Acme"
