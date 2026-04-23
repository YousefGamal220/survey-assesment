"""Load-test harness for survey.

Simulates two classes of traffic concurrently:

- `Respondent`  — the hot path at survey-launch time: login, create draft,
                  patch answers a few times, submit.
- `Analyst`     — reporting dashboards: list surveys, fetch responses.

Run against a running backend (Docker Compose or `manage.py runserver`):

    BASE=http://localhost:8000 poetry run locust --users 200 --spawn-rate 20 \\
        -H $BASE --headless -t 60s --only-summary

Before running, seed at least one user+org+published-survey; see
`scripts/seed_demo.py` (or the usage examples section in README).

Environment variables:
    SURVEY_EMAIL        — demo respondent login (default respondent@demo.test)
    SURVEY_PASSWORD     — demo password
    SURVEY_ANALYST      — analyst login email
    SURVEY_ID    — UUID of a published survey the respondent can answer
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, task


EMAIL = os.environ.get("SURVEY_EMAIL", "respondent@demo.test")
PASSWORD = os.environ.get("SURVEY_PASSWORD", "respondent-pw")
ANALYST_EMAIL = os.environ.get("SURVEY_ANALYST", "analyst@demo.test")
SURVEY_ID = os.environ.get("SURVEY_ID", "")


class _AuthedUser(HttpUser):
    abstract = True
    wait_time = between(0.2, 1.5)

    def _login(self, email: str, password: str) -> bool:
        r = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            name="login",
        )
        if r.status_code != 200:
            return False
        body = r.json()
        refresh = body["refresh"]
        membership = body["memberships"][0]

        r = self.client.post(
            "/api/v1/auth/token",
            json={"refresh": refresh, "organization_id": membership["org_id"]},
            name="token",
        )
        if r.status_code != 200:
            return False
        self.client.headers["Authorization"] = f"Bearer {r.json()['access']}"
        return True


class Respondent(_AuthedUser):
    weight = 4  # 80% of traffic

    def on_start(self):
        if not self._login(EMAIL, PASSWORD) or not SURVEY_ID:
            self.environment.runner.quit()

    @task
    def fill_and_submit(self):
        # Create/reuse draft
        r = self.client.post(
            f"/api/v1/surveys/{SURVEY_ID}/responses/",
            json={},
            name="draft:create",
        )
        if r.status_code not in (200, 201):
            return
        rid = r.json()["id"]

        # Incremental answer saves — simulates a user typing
        self.client.patch(
            f"/api/v1/surveys/{SURVEY_ID}/responses/{rid}/",
            json={"answers": {"name": f"Respondent {uuid.uuid4().hex[:6]}"}},
            name="draft:patch",
        )
        self.client.patch(
            f"/api/v1/surveys/{SURVEY_ID}/responses/{rid}/",
            json={"answers": {"age": random.randint(18, 70)}},
            name="draft:patch",
        )

        self.client.post(
            f"/api/v1/surveys/{SURVEY_ID}/responses/{rid}/submit/",
            name="draft:submit",
        )


class Analyst(_AuthedUser):
    weight = 1  # 20% of traffic

    def on_start(self):
        if not self._login(ANALYST_EMAIL, PASSWORD) or not SURVEY_ID:
            self.environment.runner.quit()

    @task(3)
    def list_surveys(self):
        self.client.get("/api/v1/surveys/?status=published", name="surveys:list")

    @task(2)
    def list_responses(self):
        self.client.get(
            f"/api/v1/surveys/{SURVEY_ID}/responses/",
            name="responses:list",
        )

    @task(1)
    def audit_log(self):
        self.client.get("/api/v1/audit-log/", name="audit:list")
