from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.models import Membership
from apps.core.permissions import _role_at_least


class IsOwnerOrAnalystReader(BasePermission):
    """Object-level guard for response detail:
    - owner can always read/modify (within status rules)
    - analyst+ can read submitted responses but not drafts
    """

    def has_object_permission(self, request, view, obj) -> bool:
        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        is_owner = obj.respondent_id == request.user.pk
        if is_owner:
            return True

        # Non-owner: must be analyst+ AND row must be submitted
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            return False
        if obj.status != obj.Status.SUBMITTED:
            return False
        return _role_at_least(membership.role, Membership.Role.ANALYST)
