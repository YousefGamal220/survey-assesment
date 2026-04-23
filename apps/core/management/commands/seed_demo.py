"""Seed a demo org, admin user, and a published survey with conditional logic.

Idempotent: running twice is a no-op (records are get_or_create'd).

Usage:
    python manage.py seed_demo --email demo@survey.test --password 'DemoPass!1'
"""

from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Membership, User
from apps.organizations.models import Organization
from apps.surveys.models import Field, Section, Survey


class Command(BaseCommand):
    help = "Seed a demo workspace + admin user + sample published survey."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo@survey.yousefgamal.com")
        parser.add_argument("--password", default="DemoPass2026!")
        parser.add_argument("--org-name", default="Survey Demo Workspace")
        parser.add_argument("--org-slug", default="survey-demo")

    @transaction.atomic
    def handle(self, *args, **opts):
        email = opts["email"].lower()
        password = opts["password"]

        org, _ = Organization.objects.get_or_create(
            slug=opts["org_slug"],
            defaults={"name": opts["org_name"], "is_active": True},
        )

        user, created = User.objects.get_or_create(email=email, defaults={"is_active": True})
        if created or not user.has_usable_password():
            user.set_password(password)
            user.save()

        Membership.objects.get_or_create(
            user=user,
            organization=org,
            defaults={"role": Membership.Role.ADMIN, "is_active": True},
        )

        if not Survey.all_objects.filter(organization=org).exists():
            self._make_sample_survey(org, user)

        self.stdout.write(self.style.SUCCESS(f"Seeded {email} / workspace {org.name}"))
        self.stdout.write(f"  password: {password}")
        self.stdout.write(f"  org id: {org.id}")

    def _make_sample_survey(self, org: Organization, author: User) -> Survey:
        survey = Survey.all_objects.create(
            organization=org,
            survey_group_id=uuid.uuid4(),
            version=1,
            title="Employee pulse check",
            description="A two-section sample showing conditional logic + sensitive fields.",
            status=Survey.Status.PUBLISHED,
            created_by=author,
        )
        # Section 1 — always visible
        s1 = Section.all_objects.create(
            organization=org, survey=survey, position=0,
            title="About you",
            description="A few quick questions to set context.",
        )
        Field.all_objects.create(
            organization=org, section=s1, position=0,
            key="employment_status", type="single_choice",
            label="What's your employment status?", required=True,
            config={
                "choices": [
                    {"value": "full_time", "label": "Full-time"},
                    {"value": "part_time", "label": "Part-time"},
                    {"value": "freelance", "label": "Freelance"},
                    {"value": "student", "label": "Student"},
                    {"value": "other", "label": "Other"},
                ]
            },
        )
        Field.all_objects.create(
            organization=org, section=s1, position=1,
            key="years_experience", type="number",
            label="Years of professional experience", required=True,
            config={"min": 0, "max": 60, "integer_only": True},
        )

        # Section 2 — only visible when currently employed
        s2 = Section.all_objects.create(
            organization=org, survey=survey, position=1,
            title="About your role",
            description="Only asked if you selected full-time, part-time, or freelance.",
            visible_when={
                "any": [
                    {"field": "employment_status", "op": "eq", "value": "full_time"},
                    {"field": "employment_status", "op": "eq", "value": "part_time"},
                    {"field": "employment_status", "op": "eq", "value": "freelance"},
                ]
            },
        )
        Field.all_objects.create(
            organization=org, section=s2, position=0,
            key="company_name", type="short_text",
            label="Company name", required=True,
        )
        Field.all_objects.create(
            organization=org, section=s2, position=1,
            key="annual_comp_usd", type="number",
            label="Annual compensation (USD)", required=False,
            config={"sensitive": True, "min": 0},
            help_text="Stored encrypted at rest. Admins see plaintext; analysts see [encrypted].",
        )
        Field.all_objects.create(
            organization=org, section=s2, position=2,
            key="work_email", type="email",
            label="Work email (optional)", required=False,
        )
        return survey
