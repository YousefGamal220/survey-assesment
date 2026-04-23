from __future__ import annotations

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Membership
from apps.accounts.tests.factories import MembershipFactory, UserFactory
from apps.core.permissions import IsOrgAdmin, IsOrgAnalyst, IsOrgViewer


def _request_with_membership(membership) -> Request:
    raw = APIRequestFactory().get("/")
    request = Request(raw)
    request.user = membership.user
    request.organization = membership.organization
    request.membership = membership
    return request


@pytest.mark.django_db
class TestHasOrgRole:
    def test_admin_passes_all(self):
        m = MembershipFactory(role=Membership.Role.ADMIN)
        req = _request_with_membership(m)
        assert IsOrgAdmin().has_permission(req, view=None) is True
        assert IsOrgAnalyst().has_permission(req, view=None) is True
        assert IsOrgViewer().has_permission(req, view=None) is True

    def test_analyst_passes_analyst_and_viewer(self):
        m = MembershipFactory(role=Membership.Role.ANALYST)
        req = _request_with_membership(m)
        assert IsOrgAdmin().has_permission(req, view=None) is False
        assert IsOrgAnalyst().has_permission(req, view=None) is True
        assert IsOrgViewer().has_permission(req, view=None) is True

    def test_viewer_passes_only_viewer(self):
        m = MembershipFactory(role=Membership.Role.VIEWER)
        req = _request_with_membership(m)
        assert IsOrgAdmin().has_permission(req, view=None) is False
        assert IsOrgAnalyst().has_permission(req, view=None) is False
        assert IsOrgViewer().has_permission(req, view=None) is True

    def test_missing_membership_denies(self):
        raw = APIRequestFactory().get("/")
        request = Request(raw)
        request.user = UserFactory.build()
        assert IsOrgViewer().has_permission(request, view=None) is False
