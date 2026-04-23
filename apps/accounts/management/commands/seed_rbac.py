from __future__ import annotations

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

ROLE_GROUPS = ("org_admin", "org_analyst", "org_viewer")


class Command(BaseCommand):
    help = "Idempotently create the three RBAC role groups."

    def handle(self, *args, **options) -> None:
        created = 0
        for name in ROLE_GROUPS:
            _, was_created = Group.objects.get_or_create(name=name)
            if was_created:
                created += 1
        self.stdout.write(self.style.SUCCESS(f"RBAC groups ensured ({created} newly created)."))
