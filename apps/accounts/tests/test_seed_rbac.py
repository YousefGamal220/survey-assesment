import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command


@pytest.mark.django_db
class TestSeedRbacCommand:
    def test_creates_three_groups(self):
        call_command("seed_rbac")
        assert set(Group.objects.values_list("name", flat=True)) >= {
            "org_admin",
            "org_analyst",
            "org_viewer",
        }

    def test_idempotent(self):
        call_command("seed_rbac")
        call_command("seed_rbac")
        assert Group.objects.filter(name__startswith="org_").count() == 3
