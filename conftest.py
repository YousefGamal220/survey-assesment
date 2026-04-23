"""Top-level pytest fixtures."""

from __future__ import annotations

import pytest
from django.core.cache import cache

from apps.core.context import _current_org_var


@pytest.fixture(scope="session")
def _dummy_tenant_table(django_db_setup, django_db_blocker):
    """Session-scoped fixture that ensures the DummyTenantModel table exists."""
    from apps.core.tests.tenant_test_model import ensure_table

    with django_db_blocker.unblock():
        ensure_table()
    yield


@pytest.fixture(autouse=True)
def _reset_tenant_contextvar():
    """Prevent contextvar leakage between tests.

    The Django test client's middleware chain normally resets the tenant
    contextvar, but some tests bypass middleware (plain APIClient calls inside
    a single process) and leave the contextvar set — poisoning later tests
    that expect a clean slate.
    """
    token = _current_org_var.set(None)
    try:
        yield
    finally:
        _current_org_var.reset(token)


@pytest.fixture(autouse=True)
def _clear_ratelimit_cache():
    """Flush django-ratelimit counters so per-test login flows start fresh."""
    cache.clear()
    yield
