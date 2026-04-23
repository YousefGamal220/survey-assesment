"""Celery app singleton. Tasks live in their own apps; autodiscovery picks them up."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("survey")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self) -> str:
    """Health-check task used to confirm the broker wiring."""
    return f"request: {self.request!r}"
