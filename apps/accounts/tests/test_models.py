import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.organizations.tests.factories import OrganizationFactory

User = get_user_model()


@pytest.mark.django_db
class TestUserManager:
    def test_create_user_with_email_lowercases_and_saves(self):
        user = User.objects.create_user(email="Alice@Example.com", password="pw12345!")
        assert user.email == "alice@example.com"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.check_password("pw12345!")

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError, match="email is required"):
            User.objects.create_user(email="", password="pw")

    def test_create_superuser_sets_flags(self):
        admin = User.objects.create_superuser(email="root@example.com", password="pw12345!")
        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_username_field_is_email(self):
        assert User.USERNAME_FIELD == "email"
        assert User.REQUIRED_FIELDS == []


@pytest.mark.django_db
class TestMembership:
    def test_creation_and_role_choices(self):
        m = MembershipFactory(role=Membership.Role.ADMIN)
        assert m.role == "admin"
        assert m.is_active is True

    def test_unique_user_org(self):
        user = UserFactory()
        org = OrganizationFactory()
        Membership.objects.create(user=user, organization=org, role="viewer")
        with pytest.raises(IntegrityError):
            Membership.objects.create(user=user, organization=org, role="admin")

    def test_roles_enum_values(self):
        assert Membership.Role.ADMIN == "admin"
        assert Membership.Role.ANALYST == "analyst"
        assert Membership.Role.VIEWER == "viewer"
