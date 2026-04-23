from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.accounts.models import Membership

_ROLE_RANK: dict[str, int] = {
    Membership.Role.VIEWER: 1,
    Membership.Role.ANALYST: 2,
    Membership.Role.ADMIN: 3,
}


def _role_at_least(actual: str | None, required: str) -> bool:
    if actual is None:
        return False
    return _ROLE_RANK.get(actual, 0) >= _ROLE_RANK[required]


class HasOrgRole(BasePermission):
    required_role: str = Membership.Role.VIEWER

    def has_permission(self, request, view) -> bool:
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        return _role_at_least(membership.role, self.required_role)


class IsOrgAdmin(HasOrgRole):
    required_role = Membership.Role.ADMIN


class IsOrgAnalyst(HasOrgRole):
    required_role = Membership.Role.ANALYST


class IsOrgViewer(HasOrgRole):
    required_role = Membership.Role.VIEWER
