from __future__ import annotations

from django.apps import AppConfig


class ResponsesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.responses"
    label = "responses"

    def ready(self) -> None:
        # Wire the Survey cache-invalidation signal, registered lazily so Django
        # has finished app-loading before the receiver hits Survey's AppConfig.
        from apps.responses import signals  # noqa: F401
