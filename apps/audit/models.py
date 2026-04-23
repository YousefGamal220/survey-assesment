from __future__ import annotations

from django.db import models


class AuditLog(models.Model):
    """Append-only record of API actions.

    Not a TenantScopedModel — we want cross-tenant visibility for super-admins
    in the Django admin, and we always filter by organization_id explicitly in
    the list view.
    """

    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        db_index=True,
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    user_email = models.EmailField(blank=True, default="")  # preserved even if user deleted
    role = models.CharField(max_length=16, blank=True, default="")
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512)
    status_code = models.PositiveSmallIntegerField()
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Flat JSON payload for extension (e.g. affected object ids).
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["method", "path"]),
        ]

    def __str__(self) -> str:
        who = self.user_email or "anonymous"
        ts = self.created_at.strftime("%Y-%m-%d %H:%M")
        return f"[{ts}] {who} {self.method} {self.path} → {self.status_code}"
