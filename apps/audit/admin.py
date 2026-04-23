from __future__ import annotations

from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user_email",
        "role",
        "method",
        "path",
        "status_code",
        "organization",
    )
    list_filter = ("method", "status_code", "organization", "role")
    search_fields = ("path", "user_email", "request_id")
    readonly_fields = tuple(f.name for f in AuditLog._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Audit log is append-only: Django admins must not prune rows.
        return False
