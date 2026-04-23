"""Development settings — intended for `docker compose up` on a developer laptop."""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import LOGGING, env

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
LOGGING["root"]["level"] = env("LOG_LEVEL", default="DEBUG")
