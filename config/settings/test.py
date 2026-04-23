"""Test settings — fast startup, eager Celery, in-memory cache."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("JWT_SIGNING_KEY", "test-jwt-signing-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("ALLOWED_HOSTS", "*")
# Fixed Fernet key so crypto round-trip tests are deterministic across CI runs.
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "XVjv8KYgrlnVe_9Z3G7Yyd4l-CChUdoDwYi-sb02jQQ=")

from .base import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
