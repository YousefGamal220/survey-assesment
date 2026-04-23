"""Production settings — hardened headers, JSON logging."""

from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import LOGGING

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LOGGING["handlers"]["stdout"]["formatter"] = "json"

# Celery beat schedule path — out of /app (owned by non-writable app user)
# into a dedicated writable named volume (see docker-compose.prod.yml).
CELERY_BEAT_SCHEDULE_FILENAME = "/var/celery/celerybeat-schedule"
